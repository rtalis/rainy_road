# app_async.py
from flask import Flask, request, send_file, Response, redirect
import psutil
from rainy_road import get_coordinates, get_bbox_graph, get_shortest_route, get_map, distance_of_coordinates_in_km,get_radius_graph
import asyncio

app = Flask(__name__)

async def generate_map_async(start_location, end_location):
    # Call the function to get coordinates
    start_latlng, end_latlng = get_coordinates(start_location, end_location)
    ram_info = psutil.virtual_memory()
    distance = distance_of_coordinates_in_km(start_latlng, end_latlng)
    print("Distancia: {} e RAM: {}".format(distance,(ram_info.available/1024/1024) ))
    if distance * 2 > ram_info.available/1024/1024:
        raise MemoryError("Insufficient memory for this request")
    try: 
        graph = get_bbox_graph(start_latlng, end_latlng, True)
        shortest_route = get_shortest_route(graph, start_latlng, end_latlng)
        shortest_route_map = get_map(graph, shortest_route)
    except:
        try: 
            print("Usando mapa sem custom filter")
            if distance * 4 > ram_info.available/1024/1024:
                raise MemoryError("Insufficient memory for this request")
            graph = get_bbox_graph(start_latlng, end_latlng, False)
            shortest_route = get_shortest_route(graph, start_latlng, end_latlng)
            shortest_route_map = get_map(graph, shortest_route)
        except:
            try:         
                print("Usando método de mapa por raio")
                if distance * 10 > ram_info.available/1024/1024:
                    raise MemoryError("Insufficient memory for this request")
                #fall to radius graph, uses more ram but will mostly find the route
                graph = get_radius_graph(start_latlng, end_latlng)
                shortest_route = get_shortest_route(graph, start_latlng, end_latlng)
                shortest_route_map = get_map(graph, shortest_route)
            except:            
                raise RuntimeError("Não foi possível gerar o mapa para estas cidades")
      
    # Save the map to a file
    map_file_path = "map.html"
    shortest_route_map.save(map_file_path)

    return map_file_path


@app.route("/", methods=["GET"])
def redirect_external():
    return redirect("https://github.com/rtalis/rainy-road-app/", code=302)

@app.route('/generate_map', methods=['GET'])
def generate_map():
    # Get city names from the query parameters
    start_location = request.args.get('start_location')
    end_location = request.args.get('end_location')

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(generate_map_async(start_location, end_location))
       
    except MemoryError as memory_error:
        # Handle memory-related errors
        return Response(
            f"<center><h1>{memory_error}</h1></center>",
            status=507,
        )
    except RuntimeError as run_error:
        return Response(
            f"<center><h1>Erro de tempo de execução: {run_error}</h1></center>",
            status=500,
        )      
    except Exception as generic_exception:
        return Response(
            f"<center><h1>Error: {generic_exception}</h1></center>",
            status=500,
        )    
    return send_file(result, mimetype='text/html')

if __name__ == "__main__":
    app.run(debug=False,host='0.0.0.0', port=5001)
