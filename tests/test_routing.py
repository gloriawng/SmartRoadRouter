from __future__ import annotations

import json
import os
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from src.api.main import RouterRequestHandler
from src.api.providers import (
    NoRoadRouteError,
    ProviderError,
    route_driving,
    search_places,
)
from src.routing.engine import (
    LocationOutsideDemoError,
    RouteRequest,
    find_route,
)


def route_request(**overrides: object) -> RouteRequest:
    payload: dict[str, object] = {
        "origin_lat": 43.4643,
        "origin_lon": -80.5204,
        "dest_lat": 43.449,
        "dest_lon": -80.475,
    }
    payload.update(overrides)
    return RouteRequest.from_payload(payload)


class RoutingTests(unittest.TestCase):
    def test_clear_weather_prefers_faster_route(self) -> None:
        result = find_route(route_request())
        self.assertEqual(
            [node["name"] for node in result["nodes"]],
            ["Uptown Waterloo", "Fast route junction", "Waterloo East"],
        )

    def test_severe_weather_prefers_sheltered_route(self) -> None:
        result = find_route(
            route_request(
                weather={
                    "snowfall_cm_per_hour": 4,
                    "wind_kmh": 50,
                    "temperature_c": -5,
                }
            )
        )
        self.assertEqual(
            [node["name"] for node in result["nodes"]],
            [
                "Uptown Waterloo",
                "Sheltered route north",
                "Sheltered route south",
                "Waterloo East",
            ],
        )

    def test_zero_safety_weight_ignores_weather_risk(self) -> None:
        result = find_route(
            route_request(
                safety_weight=0,
                weather={
                    "snowfall_cm_per_hour": 4,
                    "wind_kmh": 50,
                    "temperature_c": -5,
                },
            )
        )
        self.assertEqual(result["average_road_risk"], 0.9)
        self.assertAlmostEqual(result["weather_severity"], 1.883)

    def test_rejects_invalid_safety_weight(self) -> None:
        with self.assertRaisesRegex(ValueError, "safety_weight"):
            route_request(safety_weight=1.1)

    def test_rejects_coordinates_outside_demo_coverage(self) -> None:
        with self.assertRaises(LocationOutsideDemoError):
            find_route(
                route_request(origin_lat=43.7, origin_lon=-80.9)
            )

    def test_http_health_and_route_endpoints(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), RouterRequestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            health_request = Request(
                f"{base_url}/health",
                headers={"Origin": "http://localhost:8081"},
            )
            with urlopen(health_request) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(
                    response.headers["Access-Control-Allow-Origin"],
                    "http://localhost:8081",
                )
                self.assertEqual(json.load(response), {"status": "healthy"})

            request = Request(
                f"{base_url}/demo/route",
                data=json.dumps(
                    {
                        "origin_lat": 43.4643,
                        "origin_lon": -80.5204,
                        "dest_lat": 43.449,
                        "dest_lon": -80.475,
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request) as response:
                body = json.load(response)
                self.assertEqual(response.status, 200)
                self.assertIn("objective_cost_seconds", body)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_http_real_route_uses_osrm_and_live_weather(self) -> None:
        route_data = {
            "provider": "OpenStreetMap via self-hosted OSRM",
            "distance_km": 120.5,
            "duration_minutes": 95,
            "geometry": {"type": "LineString", "coordinates": [[-80.5, 43.4]]},
            "snapped_waypoints": [],
            "attribution": "© OpenStreetMap contributors",
        }
        weather = {
            "provider": "Open-Meteo",
            "temperature_c": -2,
            "wind_kmh": 20,
        }
        server = ThreadingHTTPServer(("127.0.0.1", 0), RouterRequestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        request = Request(
            f"http://127.0.0.1:{server.server_port}/route",
            data=json.dumps(
                {
                    "origin_lat": 43.4643,
                    "origin_lon": -80.5204,
                    "dest_lat": 44.5011,
                    "dest_lon": -80.2169,
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with (
                patch("src.api.main.route_driving", return_value=route_data),
                patch("src.api.main.get_weather", return_value=weather),
                urlopen(request) as response,
            ):
                body = json.load(response)
                self.assertEqual(response.status, 200)
            self.assertEqual(body["route"], route_data)
            self.assertEqual(body["weather"]["status"], "available")
            self.assertEqual(body["weather"]["origin"], weather)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_http_live_route_does_not_fall_back_when_osrm_is_unavailable(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), RouterRequestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        request = Request(
            f"http://127.0.0.1:{server.server_port}/route",
            data=json.dumps(
                {
                    "origin_lat": 43.4643,
                    "origin_lon": -80.5204,
                    "dest_lat": 44.5011,
                    "dest_lon": -80.2169,
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with patch(
                "src.api.main.route_driving",
                side_effect=ProviderError("router is offline"),
            ):
                with self.assertRaises(HTTPError) as response:
                    urlopen(request)
            self.assertEqual(response.exception.code, 503)
            self.assertIn("router is offline", response.exception.read().decode())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_http_geocoding_endpoint_returns_place_matches(self) -> None:
        places = [
            {
                "label": "Waterloo, Ontario, Canada",
                "latitude": 43.4643,
                "longitude": -80.5204,
            }
        ]
        server = ThreadingHTTPServer(("127.0.0.1", 0), RouterRequestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        request = Request(
            f"http://127.0.0.1:{server.server_port}/geocode?query=Waterloo",
        )
        try:
            with (
                patch("src.api.main.search_places", return_value=places),
                urlopen(request) as response,
            ):
                body = json.load(response)
            self.assertEqual(response.status, 200)
            self.assertEqual(body["places"], places)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_weather_failure_is_reported_without_faking_conditions(self) -> None:
        route_data = {
            "provider": "OpenStreetMap via self-hosted OSRM",
            "distance_km": 120.5,
            "duration_minutes": 95,
            "geometry": {"type": "LineString", "coordinates": [[-80.5, 43.4]]},
            "snapped_waypoints": [],
            "attribution": "© OpenStreetMap contributors",
        }
        server = ThreadingHTTPServer(("127.0.0.1", 0), RouterRequestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        request = Request(
            f"http://127.0.0.1:{server.server_port}/route",
            data=json.dumps(
                {
                    "origin_lat": 43.4643,
                    "origin_lon": -80.5204,
                    "dest_lat": 44.5011,
                    "dest_lon": -80.2169,
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with (
                patch("src.api.main.route_driving", return_value=route_data),
                patch(
                    "src.api.main.get_weather",
                    side_effect=ProviderError("weather service is offline"),
                ),
                urlopen(request) as response,
            ):
                body = json.load(response)
            self.assertEqual(response.status, 200)
            self.assertEqual(body["weather"]["status"], "unavailable")
            self.assertEqual(
                body["weather"]["error"], "weather service is offline"
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    @patch.dict(os.environ, {"OSRM_URL": "http://router.example/"})
    @patch(
        "src.api.providers._fetch_json",
        return_value={
            "code": "Ok",
            "routes": [
                {
                    "distance": 12345,
                    "duration": 3600,
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[-80.5, 43.4], [-80.4, 43.5]],
                    },
                }
            ],
            "waypoints": [],
        },
    )
    def test_osrm_response_is_parsed_and_uses_longitude_latitude(
        self, fetch_json
    ) -> None:
        result = route_driving((43.4, -80.5), (43.5, -80.4))
        self.assertEqual(result["distance_km"], 12.35)
        self.assertEqual(result["duration_minutes"], 60)
        self.assertEqual(
            result["geometry"]["coordinates"],
            [[-80.5, 43.4], [-80.4, 43.5]],
        )
        url = fetch_json.call_args.args[0]
        self.assertIn(
            "/route/v1/driving/-80.500000,43.400000;-80.400000,43.500000",
            url,
        )

    @patch(
        "src.api.providers._fetch_json",
        return_value={
            "results": [
                {
                    "name": "Waterloo",
                    "admin1": "Ontario",
                    "country": "Canada",
                    "latitude": 43.4643,
                    "longitude": -80.5204,
                }
            ]
        },
    )
    def test_geocoding_parses_provider_locations(self, fetch_json) -> None:
        result = search_places("Waterloo, Ontario")
        self.assertEqual(result[0]["label"], "Waterloo, Ontario, Canada")
        self.assertEqual(result[0]["latitude"], 43.4643)
        self.assertIn("Waterloo%2C+Ontario", fetch_json.call_args.args[0])

    @patch(
        "src.api.providers._fetch_json",
        return_value={"code": "NoSegment", "message": "No segment found"},
    )
    def test_osrm_no_segment_is_a_route_error(self, fetch_json) -> None:
        with self.assertRaises(NoRoadRouteError):
            route_driving((43.4, -80.5), (43.5, -80.4))
        fetch_json.assert_called_once()

    def test_http_options_preflight(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), RouterRequestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        request = Request(
            f"http://127.0.0.1:{server.server_port}/route",
            headers={
                "Origin": "http://localhost:8081",
                "Access-Control-Request-Method": "POST",
            },
            method="OPTIONS",
        )
        try:
            with urlopen(request) as response:
                self.assertEqual(response.status, 204)
                self.assertEqual(
                    response.headers["Access-Control-Allow-Origin"],
                    "http://localhost:8081",
                )
                self.assertIn("POST", response.headers["Access-Control-Allow-Methods"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_http_rejects_untrusted_browser_origin(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), RouterRequestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        request = Request(
            f"http://127.0.0.1:{server.server_port}/health",
            headers={"Origin": "https://example.com"},
        )
        try:
            with self.assertRaises(HTTPError) as response:
                urlopen(request)
            self.assertEqual(response.exception.code, 403)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_http_outside_coordinates_return_422(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), RouterRequestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        request = Request(
            f"http://127.0.0.1:{server.server_port}/demo/route",
            data=json.dumps(
                {
                    "origin_lat": 43.7,
                    "origin_lon": -80.9,
                    "dest_lat": 43.449,
                    "dest_lon": -80.475,
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.assertRaises(HTTPError) as response:
                urlopen(request)
            self.assertEqual(response.exception.code, 422)
            self.assertIn("outside the demo network", response.exception.read().decode())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
