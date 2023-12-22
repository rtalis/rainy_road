import requests
from geopy.geocoders import Nominatim
import osmnx as ox
import webbrowser
import math
import os

START_LOCATION = "Sobral, Ceará"
END_LOCATION = "Marco, Ceará"
OW_API_KEY = os.getenv('OW_API_KEY')  # OpenWeather API key
MODE = 'drive'  # bike, walk
OPTIMIZER = 'travel_time'  # lenght, travel_time


def degrees_to_radians(degrees):
    return degrees * math.pi / 180

def distance_of_coordinates_in_km(coord1, coord2):
    lat1, lon1 = coord1[:2]
    lat2, lon2 = coord2[:2]
    earth_radius = 6371
    dlat = degrees_to_radians(lat2-lat1)
    dlon = degrees_to_radians(lon2-lon1)
    lat1 = degrees_to_radians(lat1)
    lat2 = degrees_to_radians(lat2)
    a = math.sin(dlat/2) * math.sin(dlat/2) + math.sin(dlon/2) * \
        math.sin(dlon/2) * math.cos(lat1) * math.cos(lat2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return earth_radius * c 


def get_coordinates(start_location, end_location):
    locator = Nominatim(user_agent="myapp")
    try:
        start_latlng = locator.geocode(start_location).point
        end_latlng = locator.geocode(end_location).point
        if start_latlng is None or end_latlng is None:
            raise ValueError("Geocode function didn't return any coordinates.")
    except Exception as e:
        print(f"Error: {e}")
        exit(0)
    return (start_latlng, end_latlng)


def get_bbox_graph(start_latlng, end_latlng):
    ox.config(log_console=True, use_cache=True)
    north = max(start_latlng[0], end_latlng[0])
    south = min(start_latlng[0], end_latlng[0])
    east = max(start_latlng[1], end_latlng[1])
    west = min(start_latlng[1], end_latlng[1])
    buffer = 0.03 # buffer size in degrees
    north += buffer
    south -= buffer
    east += buffer
    west -= buffer
    graph = ox.graph_from_bbox(north, south, east, west, network_type=MODE, simplify=True)
    
    #ox.distance.add_edge_lengths(graph, precision=3, edges=None)
    speeds = {'primary': 100, 'secondary': 80, 'motorway': 100,
              'trunk': 100, 'residential': 40, 'tertiary': 30, 'unclassified': 20} # Add speeds to roads based on their type
    graph = ox.add_edge_speeds(graph, hwy_speeds=speeds)
    graph = ox.add_edge_travel_times(graph)
    return graph

def get_radius_graph(start_latlng, end_latlng):
    ox.config(log_console=True, use_cache=True)
    middle_latlng = (
        (start_latlng[0] + end_latlng[0])/2), ((start_latlng[1] + end_latlng[1])/2)  # get the middle spot on the route for generating the map
    radius = (distance_of_coordinates_in_km(start_latlng, end_latlng)*1000)/2
    graph = ox.graph_from_point(
        middle_latlng, dist=radius, network_type=MODE, simplify=False)
    ox.distance.add_edge_lengths(graph, precision=3, edges=None)
    speeds = {'primary': 100, 'secondary': 80, 'motorway': 100,
              'trunk': 100, 'residential': 40, 'tertiary': 40, 'unclassified': 30} # Add speeds to roads based on their type
    graph = ox.add_edge_speeds(graph, hwy_speeds=speeds)
    graph = ox.add_edge_travel_times(graph)
    return graph


def get_shortest_route(graph, start_latlng, end_latlng):
    orig_node = ox.nearest_nodes(graph, start_latlng[1], start_latlng[0])
    dest_node = ox.nearest_nodes(
        graph, end_latlng[1], end_latlng[0])
    return (ox.shortest_path(graph,
                             orig_node,
                             dest_node,
                             weight=OPTIMIZER))


def weather_at_point(lat, lng):
    if OW_API_KEY == "":
        print("\n\n\nYou need to set an Open weather API key. You can get one for free at https://home.openweathermap.org/api_keys\n\n\n")
        exit(0)
    OW_API_URL = "https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={long}&appid={appid}&units=metric".format(
        lat=lat, long=lng, appid=OW_API_KEY)
    response = requests.get(OW_API_URL)
    if response.status_code == 200:
        data = response.json()
        weather_data = data['weather']
    else:
        print("Error in the HTTP request\n")
        print(data['main'])
    return weather_data


def get_map(graph, shortest_route):
    lenght_in_nodes = len(shortest_route)
    number_of_samples = int(
        ((math.sqrt(lenght_in_nodes) / math.log10(lenght_in_nodes)))) #Get a number based on how many nodes (distance) a route has to get weather from. 
    leap = int(lenght_in_nodes/number_of_samples)
    nodes = []
    rainroad = []
    node = leap
    while node < lenght_in_nodes:
        nodes.append(node)
        node += leap
    print('Getting data from {} nodes'.format(len(nodes)))
    for node in nodes:
        index = 0 if nodes.index(node) == 0 else nodes[nodes.index(node)-1]
        node_data = graph.nodes(data=True)[shortest_route[node]]
        node_weather = weather_at_point(node_data['y'], node_data['x'])
        print('Getting weather from y={}, x={} - {}'.format(
            node_data['y'], node_data['x'], node_weather[0]['main']))
        if any(item['main'] == 'Rain' or item['main'] == 'Snow' for item in node_weather):
            for rainy_node_index in range(index, node):
                rainroad.append(shortest_route[rainy_node_index])
    shortest_route_map = ox.plot_route_folium(
        graph, shortest_route, opacity=1,color="#00c600")
    if rainroad:
        shortest_route_map = ox.plot_route_folium(
            graph, rainroad, route_map=shortest_route_map, color="#cc0000", opacity=1)
    return shortest_route_map


if __name__ == "__main__":
    start_latlng, end_latlng = get_coordinates(START_LOCATION, END_LOCATION)
    try:
        graph = get_bbox_graph(start_latlng, end_latlng)
    except:
        graph = get_radius_graph(start_latlng, end_latlng)
    graph = get_bbox_graph(start_latlng, end_latlng)
    shortest_route = get_shortest_route(graph, start_latlng, end_latlng)
    shortest_route_map = get_map(graph, shortest_route)
    shortest_route_map.save("map.html")
    webbrowser.open("map.html")
