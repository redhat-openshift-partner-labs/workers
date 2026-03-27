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

    def test_render_cluster_provisioned(self, renderer):
        """Test rendering cluster-provisioned template."""
        data = {
            "cluster_id": "test-cluster",
            "console_url": "https://console.example.com",
            "credentials_url": "https://creds.example.com",
            "credentials_password": "secret123",
            "timezone": "America/New_York",
            "expiration_date": "2026-12-31",
        }

        result = renderer.render("cluster-provisioned", data)

        assert "Welcome from OpenShift Partner Labs" in result
        assert "test-cluster" not in result  # Not used in template
        assert "https://console.example.com" in result
        assert "https://creds.example.com" in result
        assert "secret123" in result
        assert "America/New_York" in result
        assert "2026-12-31" in result

    def test_render_cluster_expiring(self, renderer):
        """Test rendering cluster-expiring template."""
        data = {
            "cluster_id": "expiring-cluster",
            "console_url": "https://console.example.com",
            "expiration_date": "2026-04-01",
        }

        result = renderer.render("cluster-expiring", data)

        assert "Your OpenShift Partner Lab is Expiring Soon" in result
        assert "expiring-cluster" in result
        assert "https://console.example.com" in result
        assert "2026-04-01" in result

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
            renderer.render("cluster-expiring", data)
