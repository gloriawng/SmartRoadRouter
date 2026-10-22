"""Clients for OpenStreetMap routing and Open-Meteo location/weather data."""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

_USER_AGENT = "SmartRoadRouter/0.2 (personal winter route planner)"
_TIMEOUT_SECONDS = 12


class ProviderError(RuntimeError):
    """Raised when a configured external data service cannot serve a request."""


class NoRoadRouteError(ProviderError):
    """Raised when the road-routing service has no driving route."""


def _fetch_json(url: str, *, timeout: int = _TIMEOUT_SECONDS) -> Any:
    request = Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ProviderError(
            f"Could not retrieve data from {urlsplit(url).hostname or 'data provider'}: "
            f"{error}"
        ) from error


def search_places(query: str) -> list[dict[str, object]]:
    query = query.strip()
    if len(query) < 3:
        raise ValueError("Enter at least 3 characters to search.")
    if len(query) > 200:
        raise ValueError("Search text must be 200 characters or fewer.")

    parameters = urlencode(
        {"name": query, "count": 5, "language": "en", "format": "json"}
    )
    payload = _fetch_json(
        f"https://geocoding-api.open-meteo.com/v1/search?{parameters}"
    )
    if not isinstance(payload, dict):
        raise ProviderError("The geocoding service returned an invalid response.")

    results = payload.get("results", [])
    if results is None:
        return []
    if not isinstance(results, list):
        raise ProviderError("The geocoding service returned an invalid results list.")

    places: list[dict[str, object]] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        latitude = result.get("latitude")
        longitude = result.get("longitude")
        name = result.get("name")
        if (
            isinstance(latitude, bool)
            or not isinstance(latitude, (int, float))
            or isinstance(longitude, bool)
            or not isinstance(longitude, (int, float))
            or not isinstance(name, str)
        ):
            continue
        details = [
            result.get(key)
            for key in ("admin1", "country")
            if isinstance(result.get(key), str)
        ]
        places.append(
            {
                "name": name,
                "label": ", ".join([name, *details]),
                "latitude": float(latitude),
                "longitude": float(longitude),
            }
        )
    return places


def _validate_coordinate(latitude: float, longitude: float) -> None:
    if not math.isfinite(latitude) or not -90 <= latitude <= 90:
        raise ValueError("Latitude must be between -90 and 90.")
    if not math.isfinite(longitude) or not -180 <= longitude <= 180:
        raise ValueError("Longitude must be between -180 and 180.")


def get_weather(latitude: float, longitude: float) -> dict[str, object]:
    _validate_coordinate(latitude, longitude)
    parameters = urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": (
                "temperature_2m,apparent_temperature,precipitation,snowfall,"
                "weather_code,wind_speed_10m,wind_gusts_10m"
            ),
            "timezone": "auto",
        }
    )
    payload = _fetch_json(f"https://api.open-meteo.com/v1/forecast?{parameters}")
    if not isinstance(payload, dict) or not isinstance(payload.get("current"), dict):
        raise ProviderError("The weather service returned an invalid response.")
    current = payload["current"]
    return {
        "provider": "Open-Meteo",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "time": current.get("time"),
        "temperature_c": current.get("temperature_2m"),
        "feels_like_c": current.get("apparent_temperature"),
        "precipitation_mm": current.get("precipitation"),
        "snowfall_cm": current.get("snowfall"),
        "weather_code": current.get("weather_code"),
        "wind_kmh": current.get("wind_speed_10m"),
        "wind_gusts_kmh": current.get("wind_gusts_10m"),
    }


def route_driving(
    origin: tuple[float, float], destination: tuple[float, float]
) -> dict[str, object]:
    origin_latitude, origin_longitude = origin
    destination_latitude, destination_longitude = destination
    _validate_coordinate(origin_latitude, origin_longitude)
    _validate_coordinate(destination_latitude, destination_longitude)

    base_url = os.environ.get("OSRM_URL", "http://127.0.0.1:5000").rstrip("/")
    coordinates = (
        f"{origin_longitude:.6f},{origin_latitude:.6f};"
        f"{destination_longitude:.6f},{destination_latitude:.6f}"
    )
    parameters = urlencode(
        {
            "overview": "full",
            "geometries": "geojson",
            "steps": "true",
            "alternatives": "false",
        }
    )
    payload = _fetch_json(
        f"{base_url}/route/v1/driving/{coordinates}?{parameters}"
    )
    if not isinstance(payload, dict):
        raise ProviderError("The road router returned an invalid response.")
    if payload.get("code") in {"NoRoute", "NoSegment"}:
        raise NoRoadRouteError("No driving route was found between these places.")
    if payload.get("code") != "Ok":
        message = payload.get("message")
        if isinstance(message, str) and message:
            raise ProviderError(f"The road router rejected the route: {message}")
        raise ProviderError("The road router returned an unsuccessful response.")

    routes = payload.get("routes")
    if not isinstance(routes, list) or not routes or not isinstance(routes[0], dict):
        raise ProviderError("The road router returned no usable route.")
    route = routes[0]
    geometry = route.get("geometry")
    if (
        not isinstance(geometry, dict)
        or geometry.get("type") != "LineString"
        or not isinstance(geometry.get("coordinates"), list)
    ):
        raise ProviderError("The road router returned invalid route geometry.")

    distance = route.get("distance")
    duration = route.get("duration")
    if (
        isinstance(distance, bool)
        or not isinstance(distance, (int, float))
        or isinstance(duration, bool)
        or not isinstance(duration, (int, float))
    ):
        raise ProviderError("The road router returned invalid distance or duration.")

    waypoints = payload.get("waypoints", [])
    snapped: list[dict[str, object]] = []
    if isinstance(waypoints, list):
        for waypoint in waypoints:
            if isinstance(waypoint, dict):
                location = waypoint.get("location")
                if (
                    isinstance(location, list)
                    and len(location) == 2
                    and all(isinstance(part, (int, float)) for part in location)
                ):
                    snapped.append(
                        {"longitude": float(location[0]), "latitude": float(location[1])}
                    )

    return {
        "provider": "OpenStreetMap via self-hosted OSRM",
        "distance_km": round(float(distance) / 1000, 2),
        "duration_minutes": round(float(duration) / 60),
        "geometry": geometry,
        "snapped_waypoints": snapped,
        "attribution": "© OpenStreetMap contributors",
    }
