# app_async.py
from flask import Flask, request, send_file, Response
import psutil
from rainy_road import get_coordinates, get_bbox_graph, get_shortest_route, get_map, distance_of_coordinates_in_km
import asyncio

app = Flask(__name__)

async def generate_map_async(start_location, end_location):
    # Call the function to get coordinates
    start_latlng, end_latlng = get_coordinates(start_location, end_location)
    ram_info = psutil.virtual_memory()
    distance = distance_of_coordinates_in_km(start_latlng, end_latlng)
    print("Distancia: {} e RAM: {}".format(distance,(ram_info.available/1024/1024) ))
    if distance * 5 > ram_info.available/1024/1024:
        raise
    graph = get_bbox_graph(start_latlng, end_latlng)
    # Get the shortest route and generate the map
    shortest_route = get_shortest_route(graph, start_latlng, end_latlng)
    shortest_route_map = get_map(graph, shortest_route)
    # Save the map to a file
    map_file_path = "map.html"
    shortest_route_map.save(map_file_path)

    return map_file_path

@app.route('/generate_map', methods=['GET'])
def generate_map():
    # Get city names from the query parameters
    start_location = request.args.get('start_location')
    end_location = request.args.get('end_location')

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(generate_map_async(start_location, end_location))
    except:
        return Response(
        "<center><h1>Sem memória para esta requisição</h1></center>",
        status=507,
        )
    
    return send_file(result, mimetype='text/html')

if __name__ == "__main__":
    app.run(debug=False)
