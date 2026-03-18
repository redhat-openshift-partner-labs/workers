"""
Lightweight HTTP health check server for Kubernetes probes.

Runs in a background thread, exposes /healthz (liveness) and /readyz (readiness).
"""

from __future__ import annotations

import logging
import threading
from functools import partial
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Callable

log = logging.getLogger("worker-etl.health")


def _make_handler(readiness_check: Callable[[], bool]) -> type[BaseHTTPRequestHandler]:
    """Create a handler class with the given readiness check bound."""

    class HealthHandler(BaseHTTPRequestHandler):
        """Simple handler for health check endpoints."""

        def do_GET(self) -> None:
            if self.path == "/healthz":
                # Liveness: always healthy if the server is running
                self._respond(200, "ok")
            elif self.path == "/readyz":
                # Readiness: check if connected to RabbitMQ
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
            # Suppress default access logging (too noisy for health checks)
            pass

    return HealthHandler


class HealthServer:
    """
    Background HTTP server for Kubernetes health probes.

    Usage:
        health = HealthServer(port=8080, readiness_check=lambda: worker.is_connected())
        health.start()
        # ... worker runs ...
        health.stop()
    """

    def __init__(self, port: int = 8080, readiness_check: Callable[[], bool] | None = None):
        self.port = port
        self._readiness_check = readiness_check or (lambda: True)
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the health server in a background thread."""
        handler_class = _make_handler(self._readiness_check)
        self._server = HTTPServer(("0.0.0.0", self.port), handler_class)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        log.info("Health server started on port %d", self.port)

    def stop(self) -> None:
        """Stop the health server."""
        if self._server:
            self._server.shutdown()
            log.info("Health server stopped")
