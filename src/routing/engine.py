"""Weather-aware routing over the prototype's local demonstration graph."""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Mapping


class LocationOutsideDemoError(ValueError):
    """Raised when a coordinate cannot be snapped to the demo graph."""


class NoRouteError(ValueError):
    """Raised when the graph contains no path between snapped locations."""


@dataclass(frozen=True)
class Weather:
    snowfall_cm_per_hour: float = 0.0
    wind_kmh: float = 0.0
    temperature_c: float = 0.0


@dataclass(frozen=True)
class RouteRequest:
    origin_lat: float
    origin_lon: float
    dest_lat: float
    dest_lon: float
    safety_weight: float = 0.7
    weather: Weather = Weather()

    @classmethod
    def from_payload(cls, payload: object) -> RouteRequest:
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")

        origin_lat = _number(payload, "origin_lat")
        origin_lon = _number(payload, "origin_lon")
        dest_lat = _number(payload, "dest_lat")
        dest_lon = _number(payload, "dest_lon")
        safety_weight = _number(payload, "safety_weight", default=0.7)

        if not -90 <= origin_lat <= 90 or not -90 <= dest_lat <= 90:
            raise ValueError("Latitude must be between -90 and 90.")
        if not -180 <= origin_lon <= 180 or not -180 <= dest_lon <= 180:
            raise ValueError("Longitude must be between -180 and 180.")
        if not 0 <= safety_weight <= 1:
            raise ValueError("safety_weight must be between 0 and 1.")

        weather_payload = payload.get("weather", {})
        if not isinstance(weather_payload, dict):
            raise ValueError("weather must be a JSON object.")
        weather = Weather(
            snowfall_cm_per_hour=_number(
                weather_payload, "snowfall_cm_per_hour", default=0.0
            ),
            wind_kmh=_number(weather_payload, "wind_kmh", default=0.0),
            temperature_c=_number(weather_payload, "temperature_c", default=0.0),
        )
        if weather.snowfall_cm_per_hour < 0:
            raise ValueError("snowfall_cm_per_hour cannot be negative.")
        if weather.wind_kmh < 0:
            raise ValueError("wind_kmh cannot be negative.")
        if not -100 <= weather.temperature_c <= 70:
            raise ValueError("temperature_c must be between -100 and 70.")

        return cls(
            origin_lat=origin_lat,
            origin_lon=origin_lon,
            dest_lat=dest_lat,
            dest_lon=dest_lon,
            safety_weight=safety_weight,
            weather=weather,
        )


@dataclass(frozen=True)
class Road:
    start: str
    end: str
    length_m: float
    speed_kmh: float
    risk_score: float


NODES: dict[str, tuple[float, float]] = {
    "Uptown Waterloo": (43.4643, -80.5204),
    "Fast route junction": (43.4570, -80.5020),
    "Waterloo East": (43.4490, -80.4750),
    "Sheltered route north": (43.4590, -80.5180),
    "Sheltered route south": (43.4530, -80.4910),
}

_ROADS = (
    Road("Uptown Waterloo", "Fast route junction", 1600, 60, 0.9),
    Road("Fast route junction", "Waterloo East", 1600, 60, 0.9),
    Road("Uptown Waterloo", "Sheltered route north", 900, 35, 0.1),
    Road("Sheltered route north", "Sheltered route south", 900, 35, 0.1),
    Road("Sheltered route south", "Waterloo East", 900, 35, 0.1),
)
_MAX_SNAP_DISTANCE_M = 3000.0
_EARTH_RADIUS_M = 6_371_000.0


def _number(
    payload: Mapping[str, object], name: str, default: float | None = None
) -> float:
    value = payload.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite.")
    return number


def _distance_m(first: tuple[float, float], second: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, first)
    lat2, lon2 = map(math.radians, second)
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(haversine))


def _nearest_node(latitude: float, longitude: float) -> str:
    point = (latitude, longitude)
    name, distance = min(
        (
            (node_name, _distance_m(point, coordinates))
            for node_name, coordinates in NODES.items()
        ),
        key=lambda candidate: candidate[1],
    )
    if distance > _MAX_SNAP_DISTANCE_M:
        raise LocationOutsideDemoError(
            "Coordinates are outside the demo network's 3 km coverage."
        )
    return name


def _weather_severity(weather: Weather) -> float:
    severity = (
        weather.snowfall_cm_per_hour / 5
        + weather.wind_kmh / 60
        + (0.25 if weather.temperature_c < 0 else 0)
    )
    return min(2.0, severity)


def find_route(request: RouteRequest) -> dict[str, object]:
    """Return the lowest generalized-cost route for a validated request."""
    origin = _nearest_node(request.origin_lat, request.origin_lon)
    destination = _nearest_node(request.dest_lat, request.dest_lon)
    severity = _weather_severity(request.weather)

    adjacency: dict[str, list[Road]] = {node: [] for node in NODES}
    for road in _ROADS:
        adjacency[road.start].append(road)
        adjacency[road.end].append(
            Road(road.end, road.start, road.length_m, road.speed_kmh, road.risk_score)
        )

    costs = {origin: 0.0}
    previous: dict[str, tuple[str, Road]] = {}
    queue: list[tuple[float, str]] = [(0.0, origin)]

    while queue:
        current_cost, current = heapq.heappop(queue)
        if current_cost > costs[current]:
            continue
        if current == destination:
            break
        for road in adjacency[current]:
            travel_seconds = road.length_m / road.speed_kmh * 3.6
            edge_cost = travel_seconds * (
                1 + request.safety_weight * severity * road.risk_score
            )
            candidate_cost = current_cost + edge_cost
            if candidate_cost < costs.get(road.end, math.inf):
                costs[road.end] = candidate_cost
                previous[road.end] = (current, road)
                heapq.heappush(queue, (candidate_cost, road.end))

    if destination not in costs:
        raise NoRouteError("No route connects the requested locations.")

    route_roads: list[Road] = []
    current = destination
    while current != origin:
        previous_node, road = previous[current]
        route_roads.append(road)
        current = previous_node
    route_roads.reverse()

    distance_m = sum(road.length_m for road in route_roads)
    estimated_travel_time_seconds = sum(
        road.length_m / road.speed_kmh * 3.6 for road in route_roads
    )
    average_risk = (
        sum(road.length_m * road.risk_score for road in route_roads) / distance_m
        if distance_m
        else 0.0
    )
    node_names = [origin]
    node_names.extend(road.end for road in route_roads)

    return {
        "origin": origin,
        "destination": destination,
        "nodes": [
            {
                "name": node_name,
                "latitude": NODES[node_name][0],
                "longitude": NODES[node_name][1],
            }
            for node_name in node_names
        ],
        "distance_km": round(distance_m / 1000, 3),
        "estimated_travel_time_seconds": round(estimated_travel_time_seconds, 1),
        "average_road_risk": round(average_risk, 3),
        "weather_severity": round(severity, 3),
        "objective_cost_seconds": round(costs[destination], 1),
    }
