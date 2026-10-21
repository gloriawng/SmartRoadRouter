"""A dependency-free local JSON API for the routing prototype."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from src.routing.engine import (
    LocationOutsideDemoError,
    NoRouteError,
    RouteRequest,
    find_route,
)

_MAX_REQUEST_BYTES = 16_384


class RouterRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "healthy"})
            return
        self._send_json(404, {"error": "Not found."})

    def do_POST(self) -> None:
        if self.path != "/route":
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
            result = find_route(route_request)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            self._send_json(400, {"error": f"Invalid JSON: {error}"})
            return
        except LocationOutsideDemoError as error:
            self._send_json(422, {"error": str(error)})
            return
        except (NoRouteError, ValueError) as error:
            self._send_json(400, {"error": str(error)})
            return

        self._send_json(200, result)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_string: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format_string % args}")


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("127.0.0.1", port), RouterRequestHandler)
    print(f"SmartRoadRouter API listening at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping SmartRoadRouter API.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
