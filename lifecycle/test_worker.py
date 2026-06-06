from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from config import Settings
from envelope import build_envelope, parse_envelope
from models import GenerateManifestsPayload, CloudProvider, NetworkType


# ── Fixtures ─────────────────────────────────────────────────────────────────

SAMPLE_PAYLOAD = {
    "cluster_name": "test-abc123",
    "base_domain": "opl.example.com",
    "hub_cluster_name": "hub-cluster",
    "hub_base_domain": "hub.example.com",
    "lab_config": {
        "openshift_version": "Latest 4.21",
        "cloud_provider": "aws",
        "region": "us-east-2",
        "worker_count": 3,
        "worker_instance_type": "m5.xlarge",
        "network_type": "OVNKubernetes",
        "ttl_hours": 240,
    },
    "users": [
        {"email": "admin@example.com", "name": "Admin User", "role": "admin"},
        {"email": "user@example.com", "name": "Regular User"},
    ],
    "auto_merge": True,
}


# ── TestSettings ─────────────────────────────────────────────────────────────


class TestSettings:
    def test_defaults(self):
        settings = Settings()
        assert settings.rabbitmq_host == "localhost"
        assert settings.rabbitmq_port == 5672
        assert settings.rabbitmq_vhost == "opl"
        assert settings.consume_queue == "lab.provision.generate-manifests"
        assert settings.publish_exchange == "opl.provision"
        assert settings.publish_routing_key == "lab.provision.manifests-complete"
        assert settings.source_id == "worker-lifecycle"
        assert settings.prefetch_count == 1
        assert settings.health_port == 8080
        assert settings.fleet_repo == "redhat-openshift-partner-labs/fleet-clusters"
        assert settings.fleet_branch == "main"

    def test_env_prefix(self):
        env = {
            "LIFECYCLE_RABBITMQ_HOST": "rabbitmq.prod",
            "LIFECYCLE_RABBITMQ_PORT": "5673",
            "LIFECYCLE_RABBITMQ_VHOST": "test-vhost",
            "LIFECYCLE_SOURCE_ID": "test-worker",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = Settings()
            assert settings.rabbitmq_host == "rabbitmq.prod"
            assert settings.rabbitmq_port == 5673
            assert settings.rabbitmq_vhost == "test-vhost"
            assert settings.source_id == "test-worker"


# ── TestEnvelope ─────────────────────────────────────────────────────────────


class TestEnvelope:
    def test_build_parse_roundtrip(self):
        payload = {"cluster_name": "test-123"}
        raw = build_envelope(
            event_type="lab.provision.manifests-complete",
            payload=payload,
            source="worker-lifecycle",
            correlation_id="corr-123",
            causation_id="cause-456",
        )
        assert isinstance(raw, bytes)

        parsed = parse_envelope(raw)
        assert parsed["event_type"] == "lab.provision.manifests-complete"
        assert parsed["source"] == "worker-lifecycle"
        assert parsed["correlation_id"] == "corr-123"
        assert parsed["causation_id"] == "cause-456"
        assert parsed["payload"] == payload
        assert "event_id" in parsed
        assert "timestamp" in parsed

    def test_auto_generates_correlation_id(self):
        raw = build_envelope(
            event_type="test",
            payload={},
            source="test",
        )
        parsed = parse_envelope(raw)
        assert parsed["correlation_id"] is not None
        assert len(parsed["correlation_id"]) > 0

    def test_includes_version_and_retry_count(self):
        raw = build_envelope(
            event_type="test",
            payload={},
            source="test",
            version="2.0.0",
            retry_count=3,
        )
        parsed = parse_envelope(raw)
        assert parsed["version"] == "2.0.0"
        assert parsed["retry_count"] == 3


# ── TestGenerateManifestsPayload ─────────────────────────────────────────────


class TestGenerateManifestsPayload:
    def test_valid_full_payload(self):
        payload = GenerateManifestsPayload.model_validate(SAMPLE_PAYLOAD)
        assert payload.cluster_name == "test-abc123"
        assert payload.base_domain == "opl.example.com"
        assert payload.lab_config.cloud_provider == CloudProvider.aws
        assert payload.lab_config.region == "us-east-2"
        assert payload.lab_config.worker_count == 3
        assert payload.lab_config.network_type == NetworkType.ovn_kubernetes
        assert len(payload.users) == 2
        assert payload.users[0].role == "admin"
        assert payload.users[1].role == "user"
        assert payload.auto_merge is True

    def test_minimal_payload(self):
        minimal = {
            "cluster_name": "min-cluster",
            "base_domain": "example.com",
            "hub_cluster_name": "hub",
            "hub_base_domain": "hub.example.com",
            "lab_config": {},
        }
        payload = GenerateManifestsPayload.model_validate(minimal)
        assert payload.cluster_name == "min-cluster"
        assert payload.gitops_repo is None
        assert payload.users == []
        assert payload.auto_merge is True
        assert payload.lab_config.cloud_provider is None

    def test_missing_cluster_name_raises(self):
        invalid = {
            "base_domain": "example.com",
            "hub_cluster_name": "hub",
            "hub_base_domain": "hub.example.com",
            "lab_config": {},
        }
        with pytest.raises(ValidationError) as exc_info:
            GenerateManifestsPayload.model_validate(invalid)
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("cluster_name",) for e in errors)

    def test_missing_lab_config_raises(self):
        invalid = {
            "cluster_name": "test",
            "base_domain": "example.com",
            "hub_cluster_name": "hub",
            "hub_base_domain": "hub.example.com",
        }
        with pytest.raises(ValidationError) as exc_info:
            GenerateManifestsPayload.model_validate(invalid)
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("lab_config",) for e in errors)

    def test_invalid_cloud_provider_raises(self):
        invalid = {**SAMPLE_PAYLOAD, "lab_config": {**SAMPLE_PAYLOAD["lab_config"], "cloud_provider": "digitalocean"}}
        with pytest.raises(ValidationError):
            GenerateManifestsPayload.model_validate(invalid)

    def test_auto_merge_defaults_true(self):
        data = {**SAMPLE_PAYLOAD}
        del data["auto_merge"]
        payload = GenerateManifestsPayload.model_validate(data)
        assert payload.auto_merge is True

    def test_user_role_defaults_user(self):
        data = {**SAMPLE_PAYLOAD, "users": [{"email": "test@example.com"}]}
        payload = GenerateManifestsPayload.model_validate(data)
        assert payload.users[0].role == "user"
        assert payload.users[0].name is None


# ── TestWorkerMessageHandling ────────────────────────────────────────────────


class TestWorkerMessageHandling:
    def _make_worker(self):
        from worker import LifecycleWorker
        settings = Settings()
        return LifecycleWorker(settings)

    def _make_delivery(self, payload: dict) -> tuple:
        body = build_envelope(
            event_type="lab.provision.generate-manifests",
            payload=payload,
            source="test",
            correlation_id="corr-test",
        )
        channel = MagicMock()
        method = MagicMock()
        method.delivery_tag = 42
        properties = MagicMock()
        return channel, method, properties, body

    def test_valid_message_acks(self):
        worker = self._make_worker()
        channel, method, properties, body = self._make_delivery(SAMPLE_PAYLOAD)

        worker._on_message(channel, method, properties, body)

        channel.basic_ack.assert_called_once_with(delivery_tag=42)
        channel.basic_nack.assert_not_called()

    def test_valid_message_publishes_result(self):
        worker = self._make_worker()
        channel, method, properties, body = self._make_delivery(SAMPLE_PAYLOAD)

        worker._on_message(channel, method, properties, body)

        channel.basic_publish.assert_called_once()
        call_kwargs = channel.basic_publish.call_args
        assert call_kwargs.kwargs["exchange"] == "opl.provision"
        assert call_kwargs.kwargs["routing_key"] == "lab.provision.manifests-complete"

        published = json.loads(call_kwargs.kwargs["body"])
        assert published["payload"]["cluster_name"] == "test-abc123"
        assert published["payload"]["branch_name"] == "provision/test-abc123"
        assert published["correlation_id"] == "corr-test"

    def test_invalid_payload_nacks(self):
        worker = self._make_worker()
        invalid_payload = {"not_a_valid": "payload"}
        channel, method, properties, body = self._make_delivery(invalid_payload)

        worker._on_message(channel, method, properties, body)

        channel.basic_nack.assert_called_once_with(delivery_tag=42, requeue=False)
        channel.basic_ack.assert_not_called()

    def test_malformed_json_nacks(self):
        worker = self._make_worker()
        channel = MagicMock()
        method = MagicMock()
        method.delivery_tag = 99
        properties = MagicMock()
        body = b"not json at all"

        worker._on_message(channel, method, properties, body)

        channel.basic_nack.assert_called_once_with(delivery_tag=99, requeue=False)

    def test_is_ready_before_connect(self):
        worker = self._make_worker()
        assert worker.is_ready() is False

    def test_shutdown_stops_consuming(self):
        worker = self._make_worker()
        worker._channel = MagicMock()
        worker._connected = True

        worker.shutdown(15, None)

        assert worker._shutting_down is True
        assert worker._connected is False
        worker._channel.stop_consuming.assert_called_once()

    def test_shutdown_idempotent(self):
        worker = self._make_worker()
        worker._channel = MagicMock()
        worker._connected = True

        worker.shutdown(15, None)
        worker.shutdown(15, None)

        worker._channel.stop_consuming.assert_called_once()
