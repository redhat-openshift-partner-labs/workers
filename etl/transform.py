"""
Core ETL transform pipeline.

Takes a raw payload (dict from AppScript body), validates it against
the schema, coerces types, splits names, generates system fields,
and produces either a normalized payload or a structured error.
"""

from __future__ import annotations

import re
import uuid
import hashlib
from datetime import datetime, timezone
from typing import Any

from .schema import ETLSchema, FieldDef


class TransformError(Exception):
    """Structured validation/transform error with machine-readable details."""

    def __init__(self, code: str, message: str, missing_fields: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.missing_fields = missing_fields or []

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            **({"missing_fields": self.missing_fields} if self.missing_fields else {}),
        }


# ── Type Coercion ─────────────────────────────────────────────────────

def _coerce_string(val: Any) -> str:
    return str(val).strip() if val is not None else ""


def _coerce_int(val: Any) -> int:
    try:
        return int(val)
    except (ValueError, TypeError):
        raise TransformError("TYPE_COERCION_FAILED", f"Cannot coerce '{val}' to int")


def _coerce_float(val: Any) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        raise TransformError("TYPE_COERCION_FAILED", f"Cannot coerce '{val}' to float")


def _coerce_bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes")
    return bool(val)


def _coerce_datetime(val: Any) -> str:
    """Parse ISO datetime string, return normalized ISO format."""
    if isinstance(val, datetime):
        return val.isoformat()
    try:
        # Handle various ISO formats from Google Sheets
        parsed = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        return parsed.isoformat()
    except (ValueError, TypeError):
        raise TransformError("INVALID_DATETIME", f"Cannot parse datetime: '{val}'")


def _coerce_email(val: Any) -> str:
    """Basic email format validation."""
    s = _coerce_string(val)
    if s and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", s):
        raise TransformError("MALFORMED_EMAIL", f"Invalid email format: '{s}'")
    return s


COERCERS = {
    "string": _coerce_string,
    "int": _coerce_int,
    "float": _coerce_float,
    "bool": _coerce_bool,
    "datetime": _coerce_datetime,
    "email": _coerce_email,
}


# ── Name Splitting ────────────────────────────────────────────────────

def _split_name_first(full_name: str) -> str:
    """Extract first name from 'First Last' or 'First Middle Last'."""
    parts = full_name.strip().split()
    return parts[0] if parts else ""


def _split_name_last(full_name: str) -> str:
    """Extract last name — everything after the first word."""
    parts = full_name.strip().split()
    return " ".join(parts[1:]) if len(parts) > 1 else ""


TRANSFORMS = {
    "split_name_first": _split_name_first,
    "split_name_last": _split_name_last,
}


# ── Field Generators ──────────────────────────────────────────────────

def _generate_uuid4() -> str:
    return str(uuid.uuid4())


def _generate_short_id() -> str:
    """Generate a short, unique, DNS-safe ID like 'opl-a7f3b2'."""
    return f"opl-{uuid.uuid4().hex[:6]}"


def _derive_cluster_name(db_row: dict) -> str:
    """
    Derive a DNS-safe cluster name from company + project.
    e.g., "Acme Corp" + "fsi-demo" → "acme-fsi-demo"
    Falls back to a hash if the result would be too long.
    """
    company = db_row.get("company_name", "unknown")
    project = db_row.get("project_name", "lab")

    # Take first word of company, lowercase, alphanumeric only
    company_slug = re.sub(r"[^a-z0-9]", "", company.lower().split()[0]) if company else "lab"
    project_slug = re.sub(r"[^a-z0-9-]", "", project.lower().replace(" ", "-"))

    name = f"{company_slug}-{project_slug}"

    # DNS label max is 63 chars; keep it shorter for readability
    if len(name) > 40:
        suffix = hashlib.sha256(name.encode()).hexdigest()[:6]
        name = f"{name[:33]}-{suffix}"

    # Ensure it starts/ends with alphanumeric
    name = re.sub(r"^[^a-z0-9]+|[^a-z0-9]+$", "", name)
    return name or "opl-lab"


GENERATORS = {
    "uuid4": lambda _row: _generate_uuid4(),
    "short_id": lambda _row: _generate_short_id(),
    "derive_cluster_name": _derive_cluster_name,
    "static": None,  # handled separately (uses field.value)
}


# ── Auto-Provision Policy ────────────────────────────────────────────

def _evaluate_standard_config(schema: ETLSchema, raw: dict, db_row: dict) -> bool:
    """
    Determine if this request qualifies for auto-provisioning.
    All is_standard_criteria fields must have values in their standard_values list,
    AND description must not contain complexity keywords.
    """
    for field_def in schema.standard_criteria_fields:
        val = _coerce_string(raw.get(field_def.source_key, ""))
        if field_def.standard_values and val not in field_def.standard_values:
            return False

    # Check description for complexity indicators
    description = _coerce_string(raw.get("description", "")).lower()
    for keyword in schema.complexity_keywords:
        if keyword.lower() in description:
            return False

    # Check if special_requests / note has content suggesting non-standard needs
    note = _coerce_string(raw.get("note", ""))
    if note and len(note) > 10:  # Non-trivial note suggests special handling
        return False

    return True


# ── Main Transform ────────────────────────────────────────────────────

def transform(schema: ETLSchema, raw: dict) -> dict:
    """
    Validate and transform a raw AppScript payload into a normalized payload.

    Returns a dict with:
      - db_columns: fields mapped to DB columns (ready for Scribe)
      - extras: fields that go into the JSONB extras column
      - is_standard_config: auto-provision policy result
      - cluster_name, cluster_id, generated_name: system-generated

    Raises TransformError on validation failure.
    """
    # ── Step 1: Check required fields ─────────────────────────────────
    missing = [
        key for key in schema.required_source_keys
        if not _coerce_string(raw.get(key, ""))
    ]
    if missing:
        raise TransformError(
            code="MISSING_REQUIRED_FIELD",
            message=f"Required fields missing or empty: {', '.join(sorted(missing))}",
            missing_fields=sorted(missing),
        )

    # ── Step 2: Validate and coerce each known field ──────────────────
    db_columns: dict[str, Any] = {}
    extras: dict[str, Any] = {}

    # Track which source keys we've processed
    processed_keys: set[str] = set()

    for source_key in schema.all_known_source_keys:
        raw_val = raw.get(source_key)
        processed_keys.add(source_key)

        for field_def in schema.fields_for(source_key):
            # Apply default if value is missing/empty
            val = raw_val
            if val is None or (isinstance(val, str) and not val.strip()):
                if field_def.default is not None:
                    val = field_def.default
                elif not field_def.required:
                    val = ""
                # If required, we already caught it in Step 1

            # Type coercion
            coercer = COERCERS.get(field_def.type, _coerce_string)
            coerced = coercer(val) if val is not None and val != "" else (val or "")

            # Apply transform (e.g., split_name_first)
            if field_def.transform and coerced:
                transformer = TRANSFORMS.get(field_def.transform)
                if transformer:
                    coerced = transformer(str(coerced))

            # Route to db_columns or extras
            if field_def.db_column:
                db_columns[field_def.db_column] = coerced
            elif field_def.db_column is None and source_key not in ("status", "evaluated_on", "timestamp", "email"):
                # Null db_column = extras JSONB (except metadata fields we intentionally drop)
                extras[source_key] = coerced

    # ── Step 3: Capture unknown fields into extras ────────────────────
    for key, val in raw.items():
        if key not in processed_keys:
            extras[key] = val

    # ── Step 4: Generate system fields ────────────────────────────────
    for gen_field in schema.generated_fields:
        if gen_field.generator == "static":
            db_columns[gen_field.db_column] = gen_field.value
        else:
            gen_fn = GENERATORS.get(gen_field.generator)
            if gen_fn:
                db_columns[gen_field.db_column] = gen_fn(db_columns)

    # ── Step 5: Compute end_date from start_date + lease ──────────────
    db_columns["end_date"] = _compute_end_date(
        db_columns.get("start_date", ""),
        db_columns.get("lease_time", ""),
    )

    # ── Step 6: Evaluate auto-provision policy ────────────────────────
    is_standard = _evaluate_standard_config(schema, raw, db_columns)

    # ── Step 7: Set defaults for fields the DB requires ───────────────
    db_columns.setdefault("partner", False)
    db_columns.setdefault("always_on", False)
    db_columns.setdefault("hold", False)

    return {
        "db_columns": db_columns,
        "extras": extras,
        "is_standard_config": is_standard,
    }


def _compute_end_date(start_date_iso: str, lease: str) -> str:
    """
    Parse lease string like '1 month (20 working days)' and compute end_date.
    Rough heuristic — Scribe can refine if needed.
    """
    from datetime import timedelta

    try:
        start = datetime.fromisoformat(start_date_iso.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return ""

    lease_lower = lease.lower()

    # Extract duration from lease strings
    if "2 week" in lease_lower:
        delta = timedelta(days=14)
    elif "1 month" in lease_lower:
        delta = timedelta(days=30)
    elif "2 month" in lease_lower:
        delta = timedelta(days=60)
    elif "3 month" in lease_lower:
        delta = timedelta(days=90)
    elif "1 week" in lease_lower:
        delta = timedelta(days=7)
    else:
        # Default: 30 days
        delta = timedelta(days=30)

    return (start + delta).isoformat()
