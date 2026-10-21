from __future__ import annotations

import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from src.api.main import RouterRequestHandler
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
            with urlopen(f"{base_url}/health") as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(json.load(response), {"status": "healthy"})

            request = Request(
                f"{base_url}/route",
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

    def test_http_outside_coordinates_return_422(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), RouterRequestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        request = Request(
            f"http://127.0.0.1:{server.server_port}/route",
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
