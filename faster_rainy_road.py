import math
import os
import webbrowser

import folium
import requests
from dotenv import load_dotenv
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim

load_dotenv()
OW_API_KEY = os.getenv("OW_API_KEY")
OSRM_URL = os.getenv("OSRM_BASE_URL", "http://router.project-osrm.org")
GW_API_KEY = os.getenv("GW_API_KEY")


def get_coordinates(start_location, end_location):
    locator = Nominatim(user_agent="rainy-road")
    start_location = (start_location or "").strip()
    end_location = (end_location or "").strip()

    if not start_location or not end_location:
        raise ValueError("Os nomes das cidades não podem estar vazios.")

    geocode = RateLimiter(locator.geocode, min_delay_seconds=1, max_retries=0)

    timeout = 10
    max_attempts = 3
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            start = geocode(start_location, timeout=timeout)
            end = geocode(end_location, timeout=timeout)
            if start is None or end is None:
                raise RuntimeError(
                    "Geocoding returned no results for one or both locations"
                )
            return (start.point, end.point)
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts:
                wait = attempt * 1.5
                time.sleep(wait)
                continue
            raise RuntimeError(f"Falha ao geocodificar as cidades: {exc}") from exc


def weather_at_point(lat, lng, travel_time):
    travel_hour = int(travel_time / 60)

    if not OW_API_KEY and not GW_API_KEY:
        raise RuntimeError(
            "Neither OpenWeather API key nor Google API KEY is set. Define at least one in the .env file."
        )

    weather_results = {
        "google": {},
        "openweather": {},
        "ow_type": None,  # Tracks if we fetched 'current' or 'forecast' data
    }

    # 1. Fetch Google Weather (Always fetch this, whether current or forecast)
    if GW_API_KEY:
        # If travel_hour is 0, we still ask Google for 1 hour to get the current conditions
        gw_hours = max(1, travel_hour)
        GW_API_URL = f"https://weather.googleapis.com/v1/forecast/hours:lookup?key={GW_API_KEY}&location.latitude={lat}&location.longitude={lng}&hours={gw_hours}"
        try:
            resp = requests.get(GW_API_URL, timeout=10)
            resp.raise_for_status()
            weather_results["google"] = resp.json()
        except requests.RequestException as exc:
            print(f"Warning: Google Weather falhou - {exc}")

    # 2. Fetch OpenWeather
    if OW_API_KEY:
        ow_endpoint = None

        # Scenario A: Current weather (trip < 1 hour) -> check both
        if travel_hour <= 1:
            ow_endpoint = "weather"
            weather_results["ow_type"] = "current"

        # Scenario B: Forecast (trip >= 1 hour) AND flag is enabled -> use forecast API
        elif travel_hour > 1:
            ow_endpoint = "forecast"
            weather_results["ow_type"] = "forecast"

        # Execute OpenWeather Call if an endpoint was selected
        if ow_endpoint:
            OW_API_URL = f"https://api.openweathermap.org/data/2.5/{ow_endpoint}?lat={lat}&lon={lng}&appid={OW_API_KEY}&units=metric"
            try:
                resp = requests.get(OW_API_URL, timeout=10)
                resp.raise_for_status()
                weather_results["openweather"] = resp.json()
            except requests.RequestException as exc:
                print(f"Warning: OpenWeather falhou - {exc}")

    return weather_results


def _is_rainy_weather(weather_data, hour):
    google_data = weather_data.get("google", {})
    ow_data = weather_data.get("openweather", {})
    ow_type = weather_data.get("ow_type")

    if google_data and "forecastHours" in google_data:
        forecasts = google_data.get("forecastHours", [])
        if forecasts:
            # hour=0 means we want index 0. hour=2 means index 1.
            target_index = max(0, min(hour - 1, len(forecasts) - 1)) if hour > 0 else 0
            target_forecast = forecasts[target_index]

            precip_prob = (
                target_forecast.get("precipitation", {})
                .get("probability", {})
                .get("percent", 0)
            )
            if precip_prob >= 50:
                return True

            if not ow_data:
                return False

    if ow_data:
        rainy_ow_conditions = {"Rain", "Snow", "Thunderstorm", "Drizzle"}

        if ow_type == "current":
            weather_array = ow_data.get("weather", [])
            for item in weather_array:
                if item.get("main") in rainy_ow_conditions:
                    print(f"OpenWeather condição atual: {item.get('main')}")
                    return True

        elif ow_type == "forecast":
            forecast_list = ow_data.get("list", [])
            if forecast_list:
                # OW returns data in 3-hour increments.
                # If travel_hour is 4, we want index 1 (hours 3-6).
                # If travel_hour is 7, we want index 2 (hours 6-9).
                target_index = min(hour // 3, len(forecast_list) - 1)
                target_forecast = forecast_list[target_index]

                weather_array = target_forecast.get("weather", [])
                for item in weather_array:
                    if item.get("main") in rainy_ow_conditions:
                        print(f"OpenWeather condição forecast: {item.get('main')}")
                        return True

    return False


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
    duration = data["routes"][0]["legs"][0]["duration"] / 60
    rainy_segments = []
    if route_len > 2:
        sample_count = int((math.sqrt(route_len) / max(math.log10(route_len), 1)) + 2)
        sample_count = max(2, min(sample_count, route_len))
        leap = max(1, route_len // sample_count)
        sample_indexes = list(range(leap, route_len, leap))
        if sample_indexes[-1] != route_len - 1:
            sample_indexes.append(route_len - 1)

        previous_index = 0
        travel_time_hours = duration / 60
        travel_time_ceil = math.ceil(travel_time_hours)
        hour_split = math.ceil(len(sample_indexes) / travel_time_ceil)  # 4
        position = 1
        for index in sample_indexes:
            hour = min(position // hour_split, travel_time_ceil - 1)  # 0,0,0,0,1,1,1,1,2,2,2,2
            lat, lon = route_points[index]
            node_weather = weather_at_point(lat, lon, duration)
            if _is_rainy_weather(node_weather, hour):
                rainy_segments.append(route_points[previous_index : index + 1])
            previous_index = index
            position += 1

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
