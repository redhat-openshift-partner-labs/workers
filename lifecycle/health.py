from __future__ import annotations

import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Callable

log = logging.getLogger("worker-lifecycle.health")


def _make_handler(readiness_check: Callable[[], bool]) -> type[BaseHTTPRequestHandler]:
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/healthz":
                self._respond(200, "ok")
            elif self.path == "/readyz":
                if readiness_check():
                    self._respond(200, "ok")
                else:
                    self._respond(503, "not ready")
            else:
                self._respond(404, "not found")

        def _respond(self, code: int, message: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(message.encode())

        def log_message(self, format: str, *args) -> None:
            pass

    return HealthHandler


class HealthServer:
    def __init__(self, port: int = 8080, readiness_check: Callable[[], bool] | None = None):
        self.port = port
        self._readiness_check = readiness_check or (lambda: True)
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        handler_class = _make_handler(self._readiness_check)
        self._server = HTTPServer(("0.0.0.0", self.port), handler_class)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        log.info("Health server started on port %d", self.port)

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            log.info("Health server stopped")
