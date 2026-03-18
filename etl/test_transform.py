"""
Tests for the ETL transform pipeline.
Uses the actual sample payload structure from the Google Sheet.
"""

import pytest
from pathlib import Path

from schema import load_schema
from transform import transform, TransformError


# Load schema from the k8s ConfigMap file
CONFIGMAP_PATH = Path(__file__).parent / "configmap-etl-schema.yaml"
# Also try standalone schema file for local dev
SCHEMA_FILE_PATH = Path(__file__).parent / "schemas" / "google-sheets-v1.yaml"


def _load_test_schema():
    """Load the Google Sheets schema for testing."""
    import yaml

    # Prefer standalone schema file if it exists
    if SCHEMA_FILE_PATH.exists():
        return load_schema(SCHEMA_FILE_PATH)

    # Fall back to extracting from ConfigMap
    raw = yaml.safe_load(CONFIGMAP_PATH.read_text())
    # ConfigMap wraps it in data.google-sheets-v1.yaml — parse the inner YAML
    inner_yaml = raw.get("data", {}).get("google-sheets-v1.yaml", "")
    # Write to a temp file and load
    tmp = Path("/tmp/test-schema.yaml")
    tmp.write_text(inner_yaml)
    return load_schema(tmp)


SCHEMA = _load_test_schema()

# ── Sample payload matching AppScript output (body only) ──────────────

SAMPLE_PAYLOAD = {
    "timestamp": "2026-03-09T16:01:57.015Z",
    "email": "submitter@example.com",
    "status": "Submitted",
    "evaluated_on": "2026-03-10T16:12:59.954Z",
    "company_name": "Acme Corp",
    "primary_contact_name": "Jane Doe",
    "primary_contact_email": "jane@acme.com",
    "secondary_contact_name": "Bob Smith",
    "secondary_contact_email": "bob@acme.com",
    "sponsor": "sponsor@redhat.com",
    "start_date": "2026-03-10T04:00:00.000Z",
    "lease": "1 month (20 working days)",
    "timezone": "America/New York City",
    "is_extension": "New Request",
    "project_name": "fsi-demo",
    "openshift_version": "Latest 4.20",
    "request_type": "OpenShift Virtualization",
    "description": "Standard OpenShift Virtualization deployment for testing.",
    "statement_of_work": "Deploy app, validate.",
    "application_type": "",
    "deployment_option": "",
    "cluster_size": "",
    "virt_size": "Standard",
    "ai_deployment_option": "",
    "ai_size": "",
    "gpu_required": "",
    "note": "",
    "extension_challenges": "",
    "extension_objectives": "",
}


class TestTransformHappyPath:
    """Verify the full transform pipeline with a valid payload."""

    def test_produces_required_db_columns(self):
        result = transform(SCHEMA, SAMPLE_PAYLOAD)
        db = result["db_columns"]

        assert db["company_name"] == "Acme Corp"
        assert db["primary_first"] == "Jane"
        assert db["primary_last"] == "Doe"
        assert db["primary_email"] == "jane@acme.com"
        assert db["secondary_first"] == "Bob"
        assert db["secondary_last"] == "Smith"
        assert db["sponsor"] == "sponsor@redhat.com"
        assert db["project_name"] == "fsi-demo"
        assert db["request_type"] == "OpenShift Virtualization"
        assert db["openshift_version"] == "Latest 4.20"
        assert db["cloud_provider"] == "aws"
        assert db["state"] == "Pending"

    def test_generates_cluster_identifiers(self):
        result = transform(SCHEMA, SAMPLE_PAYLOAD)
        db = result["db_columns"]

        assert db["cluster_id"]  # UUID, non-empty
        assert db["generated_name"].startswith("opl-")
        assert db["cluster_name"]  # derived from company + project
        assert "acme" in db["cluster_name"]

    def test_splits_names_correctly(self):
        result = transform(SCHEMA, SAMPLE_PAYLOAD)
        db = result["db_columns"]

        assert db["primary_first"] == "Jane"
        assert db["primary_last"] == "Doe"
        assert db["secondary_first"] == "Bob"
        assert db["secondary_last"] == "Smith"

    def test_three_part_name_keeps_middle_in_last(self):
        """'Mary Jane Watson' → first='Mary', last='Jane Watson'."""
        payload = {**SAMPLE_PAYLOAD, "primary_contact_name": "Mary Jane Watson"}
        result = transform(SCHEMA, payload)
        assert result["db_columns"]["primary_first"] == "Mary"
        assert result["db_columns"]["primary_last"] == "Jane Watson"

    def test_extras_populated_with_unmapped_fields(self):
        result = transform(SCHEMA, SAMPLE_PAYLOAD)
        extras = result["extras"]

        assert extras["statement_of_work"] == "Deploy app, validate."
        assert extras["virt_size"] == "Standard"
        assert extras["is_extension"] == "New Request"

    def test_end_date_computed(self):
        result = transform(SCHEMA, SAMPLE_PAYLOAD)
        assert result["db_columns"]["end_date"]  # Non-empty ISO string

    def test_metadata_fields_dropped(self):
        """timestamp, status, evaluated_on, email should NOT appear in db_columns or extras."""
        result = transform(SCHEMA, SAMPLE_PAYLOAD)
        db = result["db_columns"]
        extras = result["extras"]

        for key in ("timestamp", "status", "evaluated_on"):
            assert key not in db
            assert key not in extras

    def test_timezone_maps_to_region(self):
        result = transform(SCHEMA, SAMPLE_PAYLOAD)
        assert result["db_columns"]["region"] == "America/New York City"


class TestAutoProvisionPolicy:
    """Verify standard config detection."""

    def test_standard_config_detected(self):
        """Clean request with standard sizes → auto-provision."""
        result = transform(SCHEMA, SAMPLE_PAYLOAD)
        assert result["is_standard_config"] is True

    def test_complexity_keyword_triggers_non_standard(self):
        """Description mentioning 'assistance' → non-standard."""
        payload = {
            **SAMPLE_PAYLOAD,
            "description": "We need assistance setting up GPU nodes.",
        }
        result = transform(SCHEMA, payload)
        assert result["is_standard_config"] is False

    def test_non_standard_virt_size(self):
        payload = {**SAMPLE_PAYLOAD, "virt_size": "Custom-Large"}
        result = transform(SCHEMA, payload)
        assert result["is_standard_config"] is False

    def test_note_with_content_triggers_non_standard(self):
        payload = {
            **SAMPLE_PAYLOAD,
            "note": "Please don't decommission the old cluster yet.",
        }
        result = transform(SCHEMA, payload)
        assert result["is_standard_config"] is False


class TestValidationErrors:
    """Verify that missing/malformed data produces structured errors."""

    def test_missing_required_field_raises(self):
        payload = {**SAMPLE_PAYLOAD}
        del payload["company_name"]
        with pytest.raises(TransformError) as exc_info:
            transform(SCHEMA, payload)
        assert exc_info.value.code == "MISSING_REQUIRED_FIELD"
        assert "company_name" in exc_info.value.missing_fields

    def test_malformed_email_raises(self):
        payload = {**SAMPLE_PAYLOAD, "primary_contact_email": "not-an-email"}
        with pytest.raises(TransformError) as exc_info:
            transform(SCHEMA, payload)
        assert exc_info.value.code == "MALFORMED_EMAIL"

    def test_empty_required_field_raises(self):
        payload = {**SAMPLE_PAYLOAD, "sponsor": ""}
        with pytest.raises(TransformError) as exc_info:
            transform(SCHEMA, payload)
        assert "sponsor" in exc_info.value.missing_fields

    def test_multiple_missing_fields_reported(self):
        payload = {**SAMPLE_PAYLOAD}
        del payload["company_name"]
        del payload["sponsor"]
        del payload["primary_contact_email"]
        with pytest.raises(TransformError) as exc_info:
            transform(SCHEMA, payload)
        assert len(exc_info.value.missing_fields) == 3


class TestUnknownFields:
    """Verify that fields not in the schema are captured in extras."""

    def test_unknown_field_goes_to_extras(self):
        payload = {**SAMPLE_PAYLOAD, "some_new_column": "surprise"}
        result = transform(SCHEMA, payload)
        assert result["extras"]["some_new_column"] == "surprise"
