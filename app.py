# app_async.py
import os
import time
import uuid
from pathlib import Path

from celery import Celery
from flask import Flask, Response, jsonify, request, send_file
from flask_cors import CORS
from markupsafe import escape

from faster_rainy_road import (
    get_coordinates,
    get_route_map,
)

app = Flask(__name__)

# CORS configuration
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
if CORS_ORIGINS == "*":
    CORS(app)
else:
    CORS(app, origins=[origin.strip() for origin in CORS_ORIGINS.split(",")])

# Generated maps configuration
GENERATED_MAPS_DIR = os.getenv("GENERATED_MAPS_DIR", "generated_maps")
MAP_MAX_AGE_SECONDS = int(os.getenv("MAP_MAX_AGE_SECONDS", "7200"))


def cleanup_old_maps() -> int:
    """Delete map files older than MAP_MAX_AGE_SECONDS. Returns count of deleted files."""
    output_dir = Path(GENERATED_MAPS_DIR)
    if not output_dir.exists():
        return 0

    deleted_count = 0
    current_time = time.time()

    for map_file in output_dir.glob("map_*.html"):
        try:
            file_age = current_time - map_file.stat().st_mtime
            if file_age > MAP_MAX_AGE_SECONDS:
                map_file.unlink()
                deleted_count += 1
        except OSError:
            continue

    return deleted_count


def make_celery(flask_app: Flask) -> Celery:
    redis_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    celery = Celery(
        flask_app.import_name,
        broker=redis_url,
        backend=os.getenv("CELERY_RESULT_BACKEND", redis_url),
    )
    celery.conf.update(
        task_track_started=True,
        result_expires=int(os.getenv("CELERY_RESULT_EXPIRES", "7200")),
        broker_connection_retry_on_startup=True,
    )

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
    output_dir = Path(GENERATED_MAPS_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    cleanup_old_maps()
    file_path = output_dir / f"map_{uuid.uuid4().hex}.html"
    if isinstance(route_map, str):
        with open(file_path, "w", encoding="utf-8") as f:
            #if is an error html page
            f.write(route_map)
    else:
        route_map.save(file_path)
    
    return str(file_path)


def create_map(start_location: str, end_location: str, travel_mode: str = "auto", task=None) -> str:
    _update_progress(task, "coordinates", "Buscando coordenadas das cidades")
    start_latlng, end_latlng = get_coordinates(start_location, end_location)
    travel_mode = travel_mode

    _update_progress(task, "route", "Gerando rota com OSRM")
    _update_progress(task, "map", "Renderizando mapa com dados de chuva")
    route_map = get_route_map(start_latlng, end_latlng, travel_mode)

    _update_progress(task, "saving", "Salvando mapa em disco")
    map_file_path = _save_map_file(route_map)
    _update_progress(task, "complete", "Mapa gerado com sucesso")
    return map_file_path


def create_map_with_coordinates(start_latlng: tuple[float], end_latlng: tuple[float], travel_mode: str = "auto", task=None) -> str:
    _update_progress(task, "route", "Gerando rota com OSRM")
    _update_progress(task, "map", "Renderizando mapa com dados de chuva")
    route_map = get_route_map(start_latlng, end_latlng, travel_mode)

    _update_progress(task, "saving", "Salvando mapa em disco")
    map_file_path = _save_map_file(route_map)
    _update_progress(task, "complete", "Mapa gerado com sucesso")
    return map_file_path


@celery_app.task(bind=True, name="generate_map_task")
def generate_map_task(self, start_location: str, end_location: str, travel_mode: str = "auto") -> dict:
    try:
        map_path = create_map(start_location, end_location, travel_mode, task=self)
        return {"map_file": map_path}
    except Exception as exc:  # pragma: no cover - Celery handles logging
        _update_progress(self, "failed", str(exc))
        raise

@celery_app.task(bind=True, name="generate_map_with_coordinates_task")
def generate_map_with_coordinates_task(self, start_latlng: tuple[float], end_latlng: tuple[float], travel_mode: str = "auto") -> dict:
    start_latlng = (start_latlng[0], start_latlng[1])
    end_latlng = (end_latlng[0], end_latlng[1])
    travel_mode = travel_mode 
    print(f"Received coordinates: start={start_latlng}, end={end_latlng}, travel_mode={travel_mode}")
    try:
        map_path = create_map_with_coordinates(start_latlng, end_latlng, travel_mode,  task=self)
        return {"map_file": map_path}
    except Exception as exc:  # pragma: no cover - Celery handles logging
        _update_progress(self, "failed", str(exc))
        raise


def _sanitize_location(value):
    if value is None:
        return None
    return str(escape(value)).strip()


@app.route("/", methods=["GET"])
def index():
    return send_file("static/index.html", mimetype="text/html")


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
    travel_mode = _sanitize_location(request.args.get("travel_mode", "auto"))
    start_lat = request.args.get("start_lat")
    start_lon = request.args.get("start_lon")
    end_lat = request.args.get("end_lat")
    end_lon = request.args.get("end_lon")
    
    if start_lat and start_lon and end_lat and end_lon:
        try:
            start_latlng = (float(start_lat), float(start_lon))
            end_latlng = (float(end_lat), float(end_lon))
            task = generate_map_with_coordinates_task.apply_async(args=[start_latlng, end_latlng, travel_mode])
        except ValueError:  
            if not start_location or not end_location:
                return jsonify(
                    {"error": "As cidades de origem e destino sao obrigatorias."}
                ), 400
            task = generate_map_task.apply_async(args=[start_location, end_location, travel_mode])
    else:
        if not start_location or not end_location:
            return jsonify(
                {"error": "As cidades de origem e destino sao obrigatorias."}
            ), 400
        task = generate_map_task.apply_async(args=[start_location, end_location, travel_mode])
    
    return jsonify({"task_id": task.id}), 202


@app.route("/progress/<task_id>", methods=["GET"])
def get_task_progress(task_id: str):
    async_result = celery_app.AsyncResult(task_id)

    if async_result.state == "PENDING":
        payload = {
            "stage": "queued",
            "percent": PROGRESS_PERCENT["queued"],
            "detail": "Tarefa na fila",
        }
        return jsonify({"state": async_result.state, **payload})

    if async_result.state == "PROGRESS":
        return jsonify({"state": async_result.state, **(async_result.info or {})})

    if async_result.state == "SUCCESS":
        result = async_result.result or {}
        return jsonify(
            {"state": async_result.state, "stage": "complete", "percent": 100, **result}
        )

    detail = str(async_result.info)
    return jsonify(
        {
            "state": async_result.state,
            "stage": "failed",
            "percent": 100,
            "detail": detail,
        }
    ), 500


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
    app.run(debug=True, host="0.0.0.0", port=8000)
