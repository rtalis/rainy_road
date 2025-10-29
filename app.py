# app_async.py
import os
import uuid
from pathlib import Path

import psutil
from celery import Celery
from flask import Flask, Response, jsonify, redirect, request, send_file
from markupsafe import escape

from rainy_road import (
    distance_of_coordinates_in_km,
    get_bbox_graph,
    get_coordinates,
    get_map,
    get_radius_graph,
    get_shortest_route,
)

app = Flask(__name__)


def make_celery(flask_app: Flask) -> Celery:
    redis_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    celery = Celery(flask_app.import_name, broker=redis_url, backend=os.getenv("CELERY_RESULT_BACKEND", redis_url))
    celery.conf.update(task_track_started=True, result_expires=int(os.getenv("CELERY_RESULT_EXPIRES", "7200")))

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):  # pragma: no cover - Celery wiring
            with flask_app.app_context():
                return super().__call__(*args, **kwargs)

    celery.Task = ContextTask
    return celery


celery_app = make_celery(app)


PROGRESS_PERCENT = {
    "queued": 0,
    "coordinates": 5,
    "memory_check": 10,
    "graph_primary": 25,
    "graph_secondary": 40,
    "graph_full": 55,
    "graph_radius": 65,
    "route": 75,
    "map": 85,
    "saving": 97,
    "complete": 100,
    "failed": 100,
}



def _update_progress(task, stage: str, detail: str = "") -> None:
    if task is None:
        return
    payload = {
        "stage": stage,
        "detail": detail,
        "percent": PROGRESS_PERCENT.get(stage, 0),
    }
    task.update_state(state="PROGRESS", meta=payload)


def _save_map_file(route_map) -> str:
    output_dir = Path(os.getenv("RAINY_ROAD_OUTPUT_DIR", "generated_maps"))
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"map_{uuid.uuid4().hex}.html"
    route_map.save(file_path)
    return str(file_path)


def create_map(start_location: str, end_location: str, task=None) -> str:
    _update_progress(task, "coordinates", "Buscando coordenadas das cidades")
    start_latlng, end_latlng = get_coordinates(start_location, end_location)

    ram_info = psutil.virtual_memory()
    available_memory_mb = ram_info.available / 1024 / 1024
    distance_km = distance_of_coordinates_in_km(start_latlng, end_latlng)

    _update_progress(
        task,
        "memory_check",
        f"Distancia aproximada {distance_km:.2f} km e memoria disponivel {available_memory_mb:.0f} MB",
    )

    attempts = (
        (
            "graph_primary",
            "Gerando rota com vias principais",
            2,
            lambda: get_bbox_graph(start_latlng, end_latlng, True, True),
            "Memoria insuficiente para esta requisicao (M1). \nTente uma rota mais curta.",
        ),
        (
            "graph_secondary",
            "Gerando rota completa por bounding box",
            2,
            lambda: get_bbox_graph(start_latlng, end_latlng, True, False),
            "Memoria insuficiente para esta requisicao (M2). \nTente uma rota mais curta.",
        ),
        (
            "graph_full",
            "Gerando rota sem filtros personalizados",
            8,
            lambda: get_bbox_graph(start_latlng, end_latlng, False, False),
            "Memoria insuficiente para esta requisicao (M3). \nTente uma rota mais curta.",
        ),
        (
            "graph_radius",
            "Gerando rota por raio",
            14,
            lambda: get_radius_graph(start_latlng, end_latlng),
            "Memoria insuficiente para esta requisicao (M4). \nTente uma rota mais curta.",
        ),
    )

    last_error = None

    for stage, description, distance_multiplier, graph_builder, memory_error_msg in attempts:
        if stage == "graph_primary" and distance_km < 10:
            _update_progress(
                task,
                stage,
                "Distancia curta detectada, pulando rota com vias principais",
            )
            last_error = RuntimeError("Distancia insuficiente para rota de vias principais")
            continue

        _update_progress(task, stage, description)

        if distance_km * distance_multiplier > available_memory_mb:
            raise MemoryError(memory_error_msg)

        try:
            graph = graph_builder()
            _update_progress(task, "route", "Calculando rota mais curta")
            shortest_route = get_shortest_route(graph, start_latlng, end_latlng)
            _update_progress(task, "map", "Renderizando mapa")
            route_map = get_map(graph, shortest_route)
            break
        except MemoryError:
            raise
        except Exception as exc:
            last_error = exc
            continue
    else:
        raise RuntimeError("Nao foi possivel gerar o mapa para estas cidades") from last_error

    _update_progress(task, "saving", "Salvando mapa em disco")
    map_file_path = _save_map_file(route_map)
    _update_progress(task, "complete", "Mapa gerado com sucesso")
    return map_file_path


@celery_app.task(bind=True, name="generate_map_task")
def generate_map_task(self, start_location: str, end_location: str) -> dict:
    try:
        map_path = create_map(start_location, end_location, task=self)
        return {"map_file": map_path}
    except Exception as exc:  # pragma: no cover - Celery handles logging
        _update_progress(self, "failed", str(exc))
        raise


def _sanitize_location(value):
    if value is None:
        return None
    return str(escape(value)).strip()


@app.route("/", methods=["GET"])
def redirect_external():
    return redirect("https://github.com/rtalis/rainy-road-app/", code=302)


@app.route("/generate_map", methods=["GET"])
def generate_map_legacy():
    start_location = _sanitize_location(request.args.get("start_location"))
    end_location = _sanitize_location(request.args.get("end_location"))

    if not start_location or not end_location:
        return Response(
            "<center><h1>As cidades de origem e destino sao obrigatorias.</h1></center>",
            status=400,
            mimetype="text/html",
        )

    try:
        map_path = create_map(start_location, end_location)
    except MemoryError as memory_error:
        return Response(
            f"<center><h1>{memory_error}</h1></center>",
            status=507,
            mimetype="text/html",
        )
    except RuntimeError as runtime_error:
        return Response(
            f"<center><h1>Erro de tempo de execucao: {runtime_error}</h1></center>",
            status=500,
            mimetype="text/html",
        )
    except Exception as exc:
        return Response(
            f"<center><h1>Erro inesperado: {exc}</h1></center>",
            status=500,
            mimetype="text/html",
        )

    return send_file(map_path, mimetype="text/html")


@app.route("/generate_map_v2", methods=["GET"])
def request_map_generation():
    start_location = _sanitize_location(request.args.get("start_location"))
    end_location = _sanitize_location(request.args.get("end_location"))

    if not start_location or not end_location:
        return jsonify({"error": "As cidades de origem e destino sao obrigatorias."}), 400

    task = generate_map_task.apply_async(args=[start_location, end_location])
    return jsonify({"task_id": task.id}), 202


@app.route("/progress/<task_id>", methods=["GET"])
def get_task_progress(task_id: str):
    async_result = celery_app.AsyncResult(task_id)

    if async_result.state == "PENDING":
        payload = {"stage": "queued", "percent": PROGRESS_PERCENT["queued"], "detail": "Tarefa na fila"}
        return jsonify({"state": async_result.state, **payload})

    if async_result.state == "PROGRESS":
        return jsonify({"state": async_result.state, **(async_result.info or {})})

    if async_result.state == "SUCCESS":
        result = async_result.result or {}
        return jsonify({"state": async_result.state, "stage": "complete", "percent": 100, **result})

    detail = str(async_result.info)
    return jsonify({"state": async_result.state, "stage": "failed", "percent": 100, "detail": detail}), 500


@app.route("/result/<task_id>", methods=["GET"])
def get_task_result(task_id: str):
    async_result = celery_app.AsyncResult(task_id)

    if not async_result.successful():
        return jsonify({"error": "Tarefa ainda nao finalizada ou falhou."}), 409

    result = async_result.result or {}
    map_path = result.get("map_file")

    if not map_path or not os.path.isfile(map_path):
        return jsonify({"error": "Mapa nao encontrado para esta tarefa."}), 404

    return send_file(map_path, mimetype="text/html")


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8000)
