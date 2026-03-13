"""
Loads the ETL field schema from the ConfigMap-mounted YAML file.
Builds lookup structures for fast validation and transformation.
"""

from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class FieldDef:
    """Single field definition from the schema."""
    source_key: str
    db_column: str | None        # None = goes to extras JSONB
    type: str                    # string, int, float, bool, datetime, email
    required: bool = False
    default: str | None = None
    transform: str | None = None
    is_standard_criteria: bool = False
    standard_values: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GeneratedFieldDef:
    """Field that the ETL worker generates (not from the Sheet)."""
    db_column: str
    generator: str               # uuid4, short_id, derive_cluster_name, static
    value: str | None = None     # only used when generator=static


@dataclass
class ETLSchema:
    """Parsed schema with lookup structures for the transform pipeline."""
    version: str
    fields: list[FieldDef]
    generated_fields: list[GeneratedFieldDef]
    complexity_keywords: list[str]

    # Pre-built lookups (populated in __post_init__)
    _required_source_keys: set[str] = field(default_factory=set, init=False, repr=False)
    _fields_by_source: dict[str, list[FieldDef]] = field(default_factory=dict, init=False, repr=False)
    _standard_criteria_fields: list[FieldDef] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self):
        # One source_key can map to multiple db_columns (e.g., name → first + last)
        for f in self.fields:
            self._fields_by_source.setdefault(f.source_key, []).append(f)
            if f.required:
                self._required_source_keys.add(f.source_key)
            if f.is_standard_criteria:
                self._standard_criteria_fields.append(f)

    @property
    def required_source_keys(self) -> set[str]:
        return self._required_source_keys

    def fields_for(self, source_key: str) -> list[FieldDef]:
        """Get all field defs that consume a given source key."""
        return self._fields_by_source.get(source_key, [])

    @property
    def standard_criteria_fields(self) -> list[FieldDef]:
        return self._standard_criteria_fields

    @property
    def all_known_source_keys(self) -> set[str]:
        return set(self._fields_by_source.keys())


def load_schema(path: str | Path) -> ETLSchema:
    """Load and parse the schema YAML from the ConfigMap mount path."""
    raw = yaml.safe_load(Path(path).read_text())

    fields = [
        FieldDef(
            source_key=f["source_key"],
            db_column=f.get("db_column"),
            type=f.get("type", "string"),
            required=f.get("required", False),
            default=f.get("default"),
            transform=f.get("transform"),
            is_standard_criteria=f.get("is_standard_criteria", False),
            standard_values=f.get("standard_values", []),
        )
        for f in raw.get("fields", [])
    ]

    generated = [
        GeneratedFieldDef(
            db_column=g["db_column"],
            generator=g["generator"],
            value=g.get("value"),
        )
        for g in raw.get("generated_fields", [])
    ]

    policy = raw.get("auto_provision_policy", {})

    return ETLSchema(
        version=raw.get("version", "0.0.0"),
        fields=fields,
        generated_fields=generated,
        complexity_keywords=policy.get("complexity_keywords", []),
    )
