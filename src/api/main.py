"""A dependency-free local JSON API for the routing prototype."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from src.api.providers import (
    NoRoadRouteError,
    ProviderError,
    get_weather,
    route_driving,
    search_places,
)
from src.routing.engine import (
    LocationOutsideDemoError,
    NoRouteError,
    RouteRequest,
    find_route,
)

_MAX_REQUEST_BYTES = 16_384


class RouterRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if not self._origin_is_allowed():
            self._send_json(403, {"error": "Origin is not allowed."})
            return
        parsed_path = urlsplit(self.path)
        if parsed_path.path == "/health":
            self._send_json(200, {"status": "healthy"})
            return
        if parsed_path.path == "/geocode":
            query = parse_qs(parsed_path.query, keep_blank_values=True).get(
                "query", [""]
            )[0]
            try:
                places = search_places(query)
            except ValueError as error:
                self._send_json(400, {"error": str(error)})
                return
            except ProviderError as error:
                self._send_json(502, {"error": str(error)})
                return
            self._send_json(
                200,
                {
                    "provider": "Open-Meteo Geocoding",
                    "attribution": "Location search provided by Open-Meteo.",
                    "places": places,
                },
            )
            return
        self._send_json(404, {"error": "Not found."})

    def do_OPTIONS(self) -> None:
        if not self._origin_is_allowed():
            self._send_json(403, {"error": "Origin is not allowed."})
            return
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_POST(self) -> None:
        if not self._origin_is_allowed():
            self._send_json(403, {"error": "Origin is not allowed."})
            return
        if self.path not in {"/route", "/demo/route"}:
            self._send_json(404, {"error": "Not found."})
            return

        content_length = self.headers.get("Content-Length")
        try:
            request_size = int(content_length) if content_length is not None else -1
        except ValueError:
            self._send_json(400, {"error": "Content-Length must be an integer."})
            return
        if request_size < 0:
            self._send_json(400, {"error": "Content-Length is required."})
            return
        if request_size > _MAX_REQUEST_BYTES:
            self._send_json(413, {"error": "Request body is too large."})
            return

        try:
            payload = json.loads(self.rfile.read(request_size))
            route_request = RouteRequest.from_payload(payload)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            self._send_json(400, {"error": f"Invalid JSON: {error}"})
            return
        except ValueError as error:
            self._send_json(400, {"error": str(error)})
            return

        if self.path == "/demo/route":
            try:
                result = find_route(route_request)
            except LocationOutsideDemoError as error:
                self._send_json(422, {"error": str(error)})
                return
            except NoRouteError as error:
                self._send_json(400, {"error": str(error)})
                return
            self._send_json(200, result)
            return

        try:
            route = route_driving(
                (route_request.origin_lat, route_request.origin_lon),
                (route_request.dest_lat, route_request.dest_lon),
            )
        except NoRoadRouteError as error:
            self._send_json(422, {"error": str(error)})
            return
        except ProviderError as error:
            self._send_json(503, {"error": str(error)})
            return

        weather: dict[str, object]
        try:
            weather = {
                "status": "available",
                "origin": get_weather(
                    route_request.origin_lat, route_request.origin_lon
                ),
                "destination": get_weather(
                    route_request.dest_lat, route_request.dest_lon
                ),
            }
        except ProviderError as error:
            weather = {"status": "unavailable", "error": str(error)}

        result = {"route": route, "weather": weather}
        self._send_json(200, result)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_cors_headers(self) -> None:
        origin = self.headers.get("Origin")
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _origin_is_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        if origin is None:
            return True

        configured_origins = {
            configured.strip().rstrip("/")
            for configured in os.environ.get("CORS_ORIGINS", "").split(",")
            if configured.strip()
        }
        if origin.rstrip("/") in configured_origins:
            return True

        try:
            parsed_origin = urlsplit(origin)
        except ValueError:
            return False
        return (
            parsed_origin.scheme in {"http", "https"}
            and parsed_origin.hostname in {"localhost", "127.0.0.1", "::1"}
            and parsed_origin.username is None
            and parsed_origin.password is None
        )

    def log_message(self, format_string: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format_string % args}")


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")
    server = ThreadingHTTPServer((host, port), RouterRequestHandler)
    print(f"SmartRoadRouter API listening at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping SmartRoadRouter API.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
