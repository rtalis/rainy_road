import math
import os
import webbrowser

import folium
import requests
from dotenv import load_dotenv

load_dotenv()
OW_API_KEY = os.getenv("OW_API_KEY")
OSRM_URL = os.getenv("OSRM_BASE_URL", "http://router.project-osrm.org")


def weather_at_point(lat, lng):
    if not OW_API_KEY:
        raise RuntimeError(
            "OpenWeather API key is not set. Define OW_API_KEY environment variable."
        )

    OW_API_URL = "https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={long}&appid={appid}&units=metric".format(
        lat=lat, long=lng, appid=OW_API_KEY
    )
    try:
        resp = requests.get(OW_API_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        weather_data = data.get("weather", [])
        return weather_data
    except requests.RequestException as exc:
        raise RuntimeError(f"Erro ao consultar OpenWeather: {exc}") from exc


def _is_rainy_weather(weather_data):
    return any(
        item.get("main") in {"Rain", "Snow", "Thunderstorm"} for item in weather_data
    )


def get_osrm_route_map(start_latlng, end_latlng):
    # OSRM expects lon,lat.
    start_lon, start_lat = start_latlng[1], start_latlng[0]
    end_lon, end_lat = end_latlng[1], end_latlng[0]

    url = (
        f"{OSRM_URL}/route/v1/driving/"
        f"{start_lon},{start_lat};{end_lon},{end_lat}?overview=full&geometries=geojson"
    )

    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise RuntimeError(f"Erro ao consultar OSRM: {exc}") from exc

    if data.get("code") != "Ok":
        raise RuntimeError("OSRM could not find a route.")

    route_geometry = data["routes"][0]["geometry"]
    coordinates = route_geometry.get("coordinates", [])
    if len(coordinates) < 2:
        raise RuntimeError("OSRM retornou rota invalida.")

    route_points = [(lat, lon) for lon, lat in coordinates]
    route_len = len(route_points)

    rainy_segments = []
    if route_len > 2:
        sample_count = int((math.sqrt(route_len) / max(math.log10(route_len), 1)) + 2)
        sample_count = max(2, min(sample_count, route_len))
        leap = max(1, route_len // sample_count)
        sample_indexes = list(range(leap, route_len, leap))
        if sample_indexes[-1] != route_len - 1:
            sample_indexes.append(route_len - 1)

        previous_index = 0
        for index in sample_indexes:
            lat, lon = route_points[index]
            node_weather = weather_at_point(lat, lon)
            if _is_rainy_weather(node_weather):
                rainy_segments.append(route_points[previous_index : index + 1])
            previous_index = index

    mid_lat = (start_lat + end_lat) / 2
    mid_lon = (start_lon + end_lon) / 2
    route_map = folium.Map(
        location=[mid_lat, mid_lon], zoom_start=9, tiles="CartoDB positron"
    )
    folium.PolyLine(route_points, color="#00c600", weight=5, opacity=0.8).add_to(
        route_map
    )
    for segment in rainy_segments:
        folium.PolyLine(segment, color="#cc0000", weight=6, opacity=1).add_to(route_map)

    folium.Marker([start_lat, start_lon], popup="Start").add_to(route_map)
    folium.Marker([end_lat, end_lon], popup="End").add_to(route_map)
    return route_map


if __name__ == "__main__":
    start_latlng = (-3.121570, -40.149883)  #
    end_latlng = (-3.682920, -40.350899)
    route_map = get_osrm_route_map(start_latlng, end_latlng)
    route_map.save("route_map.html")
    webbrowser.open("route_map.html")
