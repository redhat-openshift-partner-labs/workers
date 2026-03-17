"""
Tests for payload_type routing in the ETL worker.

These tests verify that:
1. Messages without payload_type use the default schema
2. Messages with payload_type route to the correct schema
3. Messages with unknown payload_type are rejected
"""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from .schema_registry import load_schema_registry, UnknownPayloadTypeError
from .transform import transform


# Minimal schema for Google Sheets (requires company_name)
GOOGLE_SHEETS_SCHEMA = """\
version: "1.0.0"
generated_fields:
  - db_column: cluster_id
    generator: uuid4
fields:
  - source_key: company_name
    db_column: company_name
    type: string
    required: true
  - source_key: project_name
    db_column: project_name
    type: string
    required: true
auto_provision_policy:
  complexity_keywords: []
"""

# Minimal schema for Salesforce (requires account_name instead of company_name)
SALESFORCE_SCHEMA = """\
version: "1.0.0"
generated_fields:
  - db_column: cluster_id
    generator: uuid4
fields:
  - source_key: account_name
    db_column: company_name
    type: string
    required: true
  - source_key: opportunity_name
    db_column: project_name
    type: string
    required: true
auto_provision_policy:
  complexity_keywords: []
"""


@pytest.fixture
def multi_schema_registry():
    """Create a registry with multiple schemas for routing tests."""
    with TemporaryDirectory() as tmpdir:
        path = Path(tmpdir)
        (path / "google-sheets-v1.yaml").write_text(GOOGLE_SHEETS_SCHEMA)
        (path / "salesforce-v1.yaml").write_text(SALESFORCE_SCHEMA)
        yield load_schema_registry(path, default="google-sheets-v1")


class TestPayloadTypeRouting:
    """Test that payload_type correctly routes to schemas."""

    def test_none_payload_type_uses_default_schema(self, multi_schema_registry):
        """Messages without payload_type should use the default schema."""
        # Google Sheets schema expects company_name
        payload = {"company_name": "Acme Corp", "project_name": "demo"}

        schema = multi_schema_registry.get(None)
        result = transform(schema, payload)

        assert result["db_columns"]["company_name"] == "Acme Corp"

    def test_explicit_payload_type_routes_correctly(self, multi_schema_registry):
        """Messages with explicit payload_type should use that schema."""
        # Salesforce schema expects account_name (not company_name)
        payload = {"account_name": "BigCo Inc", "opportunity_name": "big-deal"}

        schema = multi_schema_registry.get("salesforce-v1")
        result = transform(schema, payload)

        assert result["db_columns"]["company_name"] == "BigCo Inc"
        assert result["db_columns"]["project_name"] == "big-deal"

    def test_wrong_payload_for_schema_fails_validation(self, multi_schema_registry):
        """Sending Google Sheets payload to Salesforce schema should fail."""
        # Google Sheets payload (has company_name, not account_name)
        payload = {"company_name": "Acme Corp", "project_name": "demo"}

        from .transform import TransformError

        schema = multi_schema_registry.get("salesforce-v1")
        with pytest.raises(TransformError) as exc_info:
            transform(schema, payload)

        # Should fail because account_name is required but missing
        assert exc_info.value.code == "MISSING_REQUIRED_FIELD"
        assert "account_name" in exc_info.value.missing_fields

    def test_unknown_payload_type_raises(self, multi_schema_registry):
        """Unknown payload_type should raise UnknownPayloadTypeError."""
        with pytest.raises(UnknownPayloadTypeError) as exc_info:
            multi_schema_registry.get("hubspot-v1")

        assert exc_info.value.payload_type == "hubspot-v1"
        assert "google-sheets-v1" in exc_info.value.available_types
        assert "salesforce-v1" in exc_info.value.available_types


class TestEnvelopePayloadType:
    """Test payload_type in message envelopes."""

    def test_build_envelope_without_payload_type(self):
        """Envelope without payload_type should not include the field."""
        from .envelope import build_envelope
        import json

        body = build_envelope(
            event_type="intake.normalized",
            payload={"test": "data"},
            source="test-worker",
        )
        envelope = json.loads(body)

        assert "payload_type" not in envelope

    def test_build_envelope_with_payload_type(self):
        """Envelope with payload_type should include it."""
        from .envelope import build_envelope
        import json

        body = build_envelope(
            event_type="intake.normalized",
            payload={"test": "data"},
            source="test-worker",
            payload_type="google-sheets-v1",
        )
        envelope = json.loads(body)

        assert envelope["payload_type"] == "google-sheets-v1"

    def test_parse_envelope_extracts_payload_type(self):
        """Parsing an envelope should correctly extract payload_type."""
        from .envelope import parse_envelope
        import json

        raw = json.dumps({
            "event_type": "intake.raw",
            "payload_type": "salesforce-v1",
            "payload": {"account_name": "Test"},
        }).encode()

        envelope = parse_envelope(raw)

        assert envelope["payload_type"] == "salesforce-v1"
