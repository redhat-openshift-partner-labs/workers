"""Tests for template rendering."""

from __future__ import annotations

import pytest

from notification.templates import TemplateRenderer


@pytest.fixture
def renderer():
    """Create template renderer."""
    return TemplateRenderer("templates")


class TestTemplateRenderer:
    """Tests for TemplateRenderer."""

    def test_render_lab_ready(self, renderer):
        """Test rendering lab_ready template."""
        data = {
            "cluster_id": "test-cluster",
            "partner_name": "Test Partner",
            "console_url": "https://console.example.com",
            "api_url": "https://api.example.com:6443",
            "credentials_url": "https://creds.example.com",
            "credentials_password": "secret123",
            "timezone": "America/New_York",
            "business_hours": "9am-5pm EST",
            "expiration_date": "2026-12-31",
            "expiration_days": 30,
        }

        result = renderer.render("lab_ready", data)

        assert "Your OpenShift Lab is Ready!" in result
        assert "test-cluster" in result
        assert "Test Partner" in result
        assert "https://console.example.com" in result
        assert "https://api.example.com:6443" in result
        assert "https://creds.example.com" in result
        assert "secret123" in result
        assert "9am-5pm EST" in result
        assert "2026-12-31" in result

    def test_render_lab_expiring(self, renderer):
        """Test rendering lab_expiring template."""
        data = {
            "cluster_id": "expiring-cluster",
            "console_url": "https://console.example.com",
            "expiration_date": "2026-04-01",
        }

        result = renderer.render("lab_expiring", data)

        assert "Your OpenShift Partner Lab is Expiring Soon" in result
        assert "expiring-cluster" in result
        assert "https://console.example.com" in result
        assert "2026-04-01" in result

    def test_render_lab_deprovisioned(self, renderer):
        """Test rendering lab_deprovisioned template."""
        data = {
            "cluster_id": "deleted-cluster",
            "deprovision_date": "2026-04-15",
            "deprovision_reason": "Lab access expired",
        }

        result = renderer.render("lab_deprovisioned", data)

        assert "Your OpenShift Lab Has Been Deprovisioned" in result
        assert "deleted-cluster" in result
        assert "2026-04-15" in result
        assert "Lab access expired" in result

    def test_missing_template(self, renderer):
        """Test error when template doesn't exist."""
        with pytest.raises(FileNotFoundError):
            renderer.render("nonexistent", {})

    def test_missing_variable(self, renderer):
        """Test error when required variable is missing."""
        data = {
            "cluster_id": "test",
            # Missing console_url and expiration_date
        }

        with pytest.raises(ValueError, match="Missing required template variable"):
            renderer.render("lab_expiring", data)
