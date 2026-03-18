"""Tests for the health check server."""

import threading
import time
import urllib.request
import pytest

from health import HealthServer


class TestHealthServer:
    """Tests for HealthServer HTTP endpoints."""

    def test_healthz_returns_200(self):
        """Liveness probe always returns 200 when server is running."""
        server = HealthServer(port=18080)
        server.start()
        try:
            time.sleep(0.1)  # Give server time to start
            with urllib.request.urlopen("http://localhost:18080/healthz") as resp:
                assert resp.status == 200
                assert resp.read() == b"ok"
        finally:
            server.stop()

    def test_readyz_returns_200_when_ready(self):
        """Readiness probe returns 200 when check passes."""
        server = HealthServer(port=18081, readiness_check=lambda: True)
        server.start()
        try:
            time.sleep(0.1)
            with urllib.request.urlopen("http://localhost:18081/readyz") as resp:
                assert resp.status == 200
                assert resp.read() == b"ok"
        finally:
            server.stop()

    def test_readyz_returns_503_when_not_ready(self):
        """Readiness probe returns 503 when check fails."""
        server = HealthServer(port=18082, readiness_check=lambda: False)
        server.start()
        try:
            time.sleep(0.1)
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen("http://localhost:18082/readyz")
            assert exc_info.value.code == 503
        finally:
            server.stop()

    def test_unknown_path_returns_404(self):
        """Unknown paths return 404."""
        server = HealthServer(port=18083)
        server.start()
        try:
            time.sleep(0.1)
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen("http://localhost:18083/unknown")
            assert exc_info.value.code == 404
        finally:
            server.stop()
