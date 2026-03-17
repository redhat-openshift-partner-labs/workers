"""
Tests for the SchemaRegistry - multi-schema loading and routing.
"""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from .schema_registry import (
    SchemaRegistry,
    UnknownPayloadTypeError,
    load_schema_registry,
)
from .schema import ETLSchema


# Minimal schema YAML for testing
MINIMAL_SCHEMA_V1 = """\
version: "1.0.0"
generated_fields: []
fields:
  - source_key: company_name
    db_column: company_name
    type: string
    required: true
auto_provision_policy:
  complexity_keywords: []
"""

MINIMAL_SCHEMA_V2 = """\
version: "2.0.0"
generated_fields: []
fields:
  - source_key: account_name
    db_column: account_name
    type: string
    required: true
auto_provision_policy:
  complexity_keywords: []
"""


@pytest.fixture
def schema_dir():
    """Create a temp directory with multiple schema files."""
    with TemporaryDirectory() as tmpdir:
        path = Path(tmpdir)
        (path / "google-sheets-v1.yaml").write_text(MINIMAL_SCHEMA_V1)
        (path / "salesforce-v1.yaml").write_text(MINIMAL_SCHEMA_V2)
        yield path


class TestSchemaRegistryLoading:
    """Test loading schemas from a directory."""

    def test_loads_all_yaml_files(self, schema_dir: Path):
        registry = load_schema_registry(schema_dir, default="google-sheets-v1")
        assert "google-sheets-v1" in registry.available_types
        assert "salesforce-v1" in registry.available_types
        assert len(registry.available_types) == 2

    def test_empty_directory_creates_empty_registry(self):
        with TemporaryDirectory() as tmpdir:
            registry = load_schema_registry(Path(tmpdir), default="nonexistent")
            assert len(registry.available_types) == 0

    def test_schema_keyed_by_filename_stem(self, schema_dir: Path):
        registry = load_schema_registry(schema_dir, default="google-sheets-v1")
        schema = registry.get("google-sheets-v1")
        assert schema.version == "1.0.0"

        schema2 = registry.get("salesforce-v1")
        assert schema2.version == "2.0.0"


class TestSchemaRegistryLookup:
    """Test schema lookup by payload_type."""

    def test_get_returns_correct_schema(self, schema_dir: Path):
        registry = load_schema_registry(schema_dir, default="google-sheets-v1")

        schema = registry.get("google-sheets-v1")
        assert isinstance(schema, ETLSchema)
        assert schema.version == "1.0.0"

    def test_none_payload_type_uses_default(self, schema_dir: Path):
        registry = load_schema_registry(schema_dir, default="google-sheets-v1")

        schema = registry.get(None)
        assert schema.version == "1.0.0"

    def test_unknown_payload_type_raises(self, schema_dir: Path):
        registry = load_schema_registry(schema_dir, default="google-sheets-v1")

        with pytest.raises(UnknownPayloadTypeError) as exc_info:
            registry.get("hubspot-v1")

        assert exc_info.value.payload_type == "hubspot-v1"
        assert "google-sheets-v1" in exc_info.value.available_types
        assert "salesforce-v1" in exc_info.value.available_types

    def test_unknown_default_raises_on_none_lookup(self, schema_dir: Path):
        registry = load_schema_registry(schema_dir, default="nonexistent")

        with pytest.raises(UnknownPayloadTypeError) as exc_info:
            registry.get(None)

        assert exc_info.value.payload_type == "nonexistent"


class TestUnknownPayloadTypeError:
    """Test the error class structure."""

    def test_error_has_machine_readable_code(self):
        err = UnknownPayloadTypeError("foo", ["bar", "baz"])
        assert err.code == "UNKNOWN_PAYLOAD_TYPE"

    def test_error_to_dict(self):
        err = UnknownPayloadTypeError("foo", ["bar", "baz"])
        d = err.to_dict()

        assert d["code"] == "UNKNOWN_PAYLOAD_TYPE"
        assert d["payload_type"] == "foo"
        assert d["available_types"] == ["bar", "baz"]
        assert "message" in d


class TestBackwardCompatibility:
    """Test backward compatibility with single-schema mode."""

    def test_single_schema_file_fallback(self, schema_dir: Path):
        """When only one schema exists, it should work as before."""
        # Remove one schema
        (schema_dir / "salesforce-v1.yaml").unlink()

        registry = load_schema_registry(schema_dir, default="google-sheets-v1")
        schema = registry.get(None)
        assert schema.version == "1.0.0"

    def test_registry_with_deprecated_schema_path(self):
        """Test loading a single schema file directly (for backward compat)."""
        from .schema_registry import load_single_schema_as_registry

        with TemporaryDirectory() as tmpdir:
            schema_file = Path(tmpdir) / "schema.yaml"
            schema_file.write_text(MINIMAL_SCHEMA_V1)

            registry = load_single_schema_as_registry(
                schema_file, payload_type="legacy"
            )
            assert "legacy" in registry.available_types
            schema = registry.get("legacy")
            assert schema.version == "1.0.0"
