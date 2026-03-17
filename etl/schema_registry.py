"""
Schema registry for multi-payload-type support.

Loads multiple ETL schemas from a directory and provides routing
based on the `payload_type` field in message envelopes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .schema import ETLSchema, load_schema


class UnknownPayloadTypeError(Exception):
    """Raised when a payload_type doesn't match any loaded schema."""

    code = "UNKNOWN_PAYLOAD_TYPE"

    def __init__(self, payload_type: str, available_types: list[str]):
        self.payload_type = payload_type
        self.available_types = available_types
        self.message = (
            f"Unknown payload_type '{payload_type}'. "
            f"Available types: {', '.join(available_types) or 'none'}"
        )
        super().__init__(self.message)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "payload_type": self.payload_type,
            "available_types": self.available_types,
        }


@dataclass
class SchemaRegistry:
    """
    Registry holding multiple ETLSchema instances, keyed by payload_type.

    Usage:
        registry = load_schema_registry(Path("/etc/etl-schemas"), default="google-sheets-v1")
        schema = registry.get(payload_type)  # None falls back to default
    """

    _schemas: dict[str, ETLSchema]
    default_payload_type: str

    @property
    def available_types(self) -> list[str]:
        """List of all loaded payload types."""
        return list(self._schemas.keys())

    def get(self, payload_type: str | None) -> ETLSchema:
        """
        Return schema for the given payload_type.

        Args:
            payload_type: The payload type from the message envelope.
                          If None, uses the default_payload_type.

        Returns:
            The ETLSchema for this payload type.

        Raises:
            UnknownPayloadTypeError: If the payload_type is not found.
        """
        key = payload_type or self.default_payload_type
        if key not in self._schemas:
            raise UnknownPayloadTypeError(key, self.available_types)
        return self._schemas[key]


def load_schema_registry(schema_dir: Path, default: str) -> SchemaRegistry:
    """
    Load all *.yaml files from a directory as schemas.

    Each file becomes a schema keyed by its filename stem (without extension).
    For example, `google-sheets-v1.yaml` becomes payload_type `google-sheets-v1`.

    Args:
        schema_dir: Directory containing schema YAML files.
        default: Default payload_type to use when envelope lacks one.

    Returns:
        SchemaRegistry with all loaded schemas.
    """
    schemas: dict[str, ETLSchema] = {}
    for path in Path(schema_dir).glob("*.yaml"):
        schemas[path.stem] = load_schema(path)
    return SchemaRegistry(_schemas=schemas, default_payload_type=default)


def load_single_schema_as_registry(
    schema_path: Path, payload_type: str
) -> SchemaRegistry:
    """
    Load a single schema file as a registry (backward compatibility).

    This supports the deprecated `schema_path` setting by wrapping
    a single schema in a registry.

    Args:
        schema_path: Path to the schema YAML file.
        payload_type: The payload_type key to use for this schema.

    Returns:
        SchemaRegistry containing just this one schema.
    """
    schema = load_schema(schema_path)
    return SchemaRegistry(
        _schemas={payload_type: schema},
        default_payload_type=payload_type,
    )
