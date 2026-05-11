from datetime import datetime, time, timedelta, timezone
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
OM_ENABLED = os.getenv("OPEN_METEO_ENABLED", "False").lower() in ("true", "1", "yes")


def get_coordinates(start_location, end_location):
    locator = Nominatim(user_agent="rainy-road")
    start_location = (start_location or "").strip()
    end_location = (end_location or "").strip()

    if not start_location or not end_location:
        raise ValueError("Os nomes das cidades não podem estar vazios.")

    geocode = RateLimiter(locator.geocode, min_delay_seconds=1, max_retries=0)

    timeout = 10
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            start = geocode(start_location, timeout=timeout)
            end = geocode(end_location, timeout=timeout)
            if start is None or end is None:
                raise RuntimeError("Geocoding returned no results for one or both locations")
            return (start.point, end.point)
        except Exception as exc:
            if attempt < max_attempts:
                time.sleep(attempt * 1.5)
                continue
            raise RuntimeError(f"Falha ao geocodificar as cidades: {exc}") from exc


def weather_at_point(lat, lng, estimated_arrival_minutes):
    if not OW_API_KEY and not GW_API_KEY and not OM_ENABLED:
        raise RuntimeError(
            "No weather services configured. Define OW_API_KEY, GW_API_KEY, or set OPEN_METEO_ENABLED=True in .env"
        )

    weather_results = {
        "google": {},
        "openweather": {},
        "open_meteo": {},
        "ow_type": None,
    }

    if GW_API_KEY:
        gw_hours = max(1, estimated_arrival_minutes // 60)
        GW_API_URL = f"https://weather.googleapis.com/v1/forecast/hours:lookup?key={GW_API_KEY}&location.latitude={lat}&location.longitude={lng}&hours={gw_hours}"
        try:
            resp = requests.get(GW_API_URL, timeout=10)
            resp.raise_for_status()
            weather_results["google"] = resp.json()
        except requests.RequestException as exc:
            print(f"Warning: Google Weather falhou - {exc}")

    if OW_API_KEY:
        ow_endpoint = None
        if estimated_arrival_minutes <= 60:
            ow_endpoint = "weather"
            weather_results["ow_type"] = "current"
        elif estimated_arrival_minutes > 60:
            ow_endpoint = "forecast"
            weather_results["ow_type"] = "forecast"

        if ow_endpoint:
            OW_API_URL = f"https://api.openweathermap.org/data/2.5/{ow_endpoint}?lat={lat}&lon={lng}&appid={OW_API_KEY}&units=metric"
            try:
                resp = requests.get(OW_API_URL, timeout=10)
                resp.raise_for_status()
                weather_results["openweather"] = resp.json()
            except requests.RequestException as exc:
                print(f"Warning: OpenWeather falhou - {exc}")

    return weather_results


def _get_weather_status(weather_data, estimated_arrival_minutes):
    """
    Returns a dict: {"is_rainy": bool, "volume": float, "prob": int, "time": str}
    """
    google_data = weather_data.get("google", {})
    ow_data = weather_data.get("openweather", {})
    om_data = weather_data.get("open_meteo", {})
    ow_type = weather_data.get("ow_type")

    exact_arrival_utc = datetime.now(timezone.utc) + timedelta(minutes=estimated_arrival_minutes)
    local_display_time = (exact_arrival_utc - timedelta(hours=3)).strftime("%H:%M")

    # Default safe return
    no_rain = {"is_rainy": False, "volume": 0.0, "prob": 0, "time": local_display_time}

    # 1. Google check
    if google_data and "forecastHours" in google_data:
        forecasts = google_data.get("forecastHours", [])
        if forecasts:
            target_index = max(0, min(int(estimated_arrival_minutes // 60 - 1), len(forecasts) - 1)) if estimated_arrival_minutes > 0 else 0
            target_forecast = forecasts[target_index]

            precip_prob = target_forecast.get("precipitation", {}).get("probability", {}).get("percent", 0)
            rain_mm = target_forecast.get("precipitation", {}).get("qpf", {}).get("quantity", 0)

            if precip_prob >= 50 and rain_mm > 0.2:
                return {"is_rainy": True, "volume": rain_mm, "prob": precip_prob, "time": local_display_time, "provider": "google"}

            if not ow_data and not om_data:
                return no_rain

    # 2. Open-Meteo check
    if om_data and "hourly" in om_data:
        hourly = om_data["hourly"]
        times = hourly.get("time", [])
        probs = hourly.get("precipitation_probability", [])
        precips = hourly.get("precipitation", [])

        # Rounding for API lookup (Strictly UTC)
        lookup_time = exact_arrival_utc
        if lookup_time.minute >= 30:
            lookup_time += timedelta(hours=1)
        arrival_time_str = lookup_time.strftime("%Y-%m-%dT%H:00")

        try:
            target_index = times.index(arrival_time_str)
            precip_prob = probs[target_index]
            rain_mm = precips[target_index]

            if precip_prob >= 50 and rain_mm > 0.2:
                return {"is_rainy": True, "volume": rain_mm, "prob": precip_prob, "time": local_display_time, "provider": "open_meteo"}
            else:
                no_rain =  {"is_rainy": False, "volume": rain_mm, "prob": precip_prob, "time": local_display_time}
        except ValueError:
            pass

    # 3. OpenWeather Check (Fallback)
    if ow_data:
        rainy_ow_conditions = {"Rain", "Snow", "Thunderstorm"}
        
        if ow_type == "current":
            weather_array = ow_data.get("weather", [])
            for item in weather_array:
                if item.get("main") in rainy_ow_conditions:
                    # Dummy high values since OW doesn't give us exact prob/vol here
                    return {"is_rainy": True, "volume": 2.5, "prob": 90, "time": local_display_time}
                else:
                    return no_rain

        elif ow_type == "forecast":
            forecast_list = ow_data.get("list", [])
            if forecast_list:
                target_index = int(min(estimated_arrival_minutes // 180, len(forecast_list) - 1))
                weather_array = forecast_list[target_index].get("weather", [])
                pop = forecast_list[target_index].get("pop", 0.9) * 100 
                rain_mm = forecast_list[target_index].get("rain", {}).get("3h", 0) 
                for item in weather_array:
                    if item.get("main") in rainy_ow_conditions: 
                        return {"is_rainy": True, "volume": rain_mm, "prob": pop, "time": local_display_time, "provider": "openweather"}
                    else:
                        return no_rain

    return no_rain


def get_lats_longs_from_route(sample_indexes, route_points):
    lats = [route_points[i][0] for i in sample_indexes]
    lons = [route_points[i][1] for i in sample_indexes]
    return ",".join(map(str, lats)), ",".join(map(str, lons))


def get_open_meteo_batch_weather(lats, lons):
    om_url = f"https://api.open-meteo.com/v1/forecast?latitude={lats}&longitude={lons}&hourly=precipitation_probability,precipitation,rain&forecast_days=2"
    try:
        om_resp = requests.get(om_url, timeout=10)
        om_resp.raise_for_status()
        data = om_resp.json()
        return [data] if isinstance(data, dict) else data
    except requests.RequestException as exc:
        print(f"Warning: Bulk Open-Meteo request failed - {exc}")
        return []


def get_rain_color(volume_mm):
    """Returns a color hex code based on rain intensity."""
    if volume_mm <= 0.2: return "#00c600"  # Green (Light or No Rain)
    if volume_mm <= 0.5: return "#3388ff"  # Light Blue (Drizzle)
    if volume_mm <= 3.0: return "#800080"  # Purple (Moderate Rain)
    return "#cc0000"                       # Deep Red (Heavy Rain / Danger)


def get_osrm_route_map(start_latlng, end_latlng):
    start_lon, start_lat = start_latlng[1], start_latlng[0]
    end_lon, end_lat = end_latlng[1], end_latlng[0]

    url = f"{OSRM_URL}/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}?overview=full&geometries=geojson"

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
    segment_data = []
    
    if route_len >= 2:
        sample_count = int((math.sqrt(route_len) / max(math.log10(route_len), 1)) + 2)
        sample_count = max(2, min(sample_count, route_len))
        leap = max(1, route_len // sample_count)
        sample_indexes = list(range(leap, route_len, leap))
        if sample_indexes[-1] != route_len - 1:
            sample_indexes.append(route_len - 1)
            
        open_meteo_weather_data = []
        lats, longs = get_lats_longs_from_route(sample_indexes, route_points)
        
        if OM_ENABLED:
            open_meteo_weather_data = get_open_meteo_batch_weather(lats, longs)

        previous_index = 0
        for i, index in enumerate(sample_indexes):
            lat, lon = route_points[index]
            
            route_fraction = index / route_len
            estimated_arrival_minutes = route_fraction * duration
            
            node_weather = weather_at_point(lat, lon, estimated_arrival_minutes)
            
            if open_meteo_weather_data and i < len(open_meteo_weather_data):
                node_weather["open_meteo"] = open_meteo_weather_data[i]
                
            # Get the detailed storm status
            status = _get_weather_status(node_weather, estimated_arrival_minutes)
            
            if status:
                
                if status["is_rainy"] == True:
                    rainy_segments.append({
                        "coords": route_points[previous_index : index + 1],
                        "volume": status["volume"],
                        "prob": status["prob"],
                        "time": status["time"]
                    })
                segment_data.append({ 
                        "coords": route_points[previous_index : index + 1],
                        "volume": status["volume"],
                        "prob": status["prob"],
                        "time": status["time"]
                    })
                
            previous_index = index


    mid_lat, mid_lon = (start_lat + end_lat) / 2, (start_lon + end_lon) / 2
    route_map = folium.Map(location=[mid_lat, mid_lon], zoom_start=9, tiles="CartoDB positron")
    
    for segment in segment_data:
        # Determine color based on how bad the storm is
        segment_color = get_rain_color(segment["volume"])
        
        # Build the HTML Tooltip
        tooltip_html = f"""
        <div style='font-family: Arial, sans-serif; font-size: 13px; padding: 4px;'>
            <b>🌧️ Alerta de Chuva</b><br>
            <hr style='margin: 4px 0; border: 0; border-top: 1px solid #ccc;'>
            Chegada aprox: <b>{segment['time']}</b><br>
            Volume: <b>{segment['volume']} mm/h</b><br>
            Probabilidade: <b>{segment['prob']}%</b><br>
            Provedor: <b>{segment['provider'] or 'N/A'}</b>
        </div>
        """
        
        folium.PolyLine(
            segment["coords"], 
            color=segment_color, 
            weight=7, # Made it slightly thicker so it stands out over the green line
            opacity=1,
            tooltip=folium.Tooltip(tooltip_html)
        ).add_to(route_map)

    folium.Marker([start_lat, start_lon], popup="Start").add_to(route_map)
    folium.Marker([end_lat, end_lon], popup="End").add_to(route_map)
    
    return route_map


if __name__ == "__main__":
    start_latlng = (-3.121570, -40.149883)
    end_latlng = (-3.682920, -40.350899)
    route_map = get_osrm_route_map(start_latlng, end_latlng)
    route_map.save("route_map.html")
    webbrowser.open("route_map.html")