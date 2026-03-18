# Developer Guide

This guide covers local development setup, code conventions, and how to extend the ETL worker with new transforms, generators, and field mappings.

## Prerequisites

- Python 3.12+
- RabbitMQ (for integration testing)
- uv or pip for dependency management

## Local Development Setup

### 1. Clone and Install

```bash
cd workers/etl

# Using uv (recommended)
uv sync

# Or using pip
pip install -e '.[dev]'
```

### 2. Run Tests

```bash
# Using uv
uv run pytest test_transform.py -v

# With coverage
uv run pytest test_transform.py -v --cov=. --cov-report=term-missing

# Or using pytest directly
pytest test_transform.py -v
```

### 3. Run the Worker Locally

Requires RabbitMQ running at `localhost:5672`:

```bash
# Start RabbitMQ (using Docker/Podman)
podman run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management

# Run the worker
uv run python -m worker

# Or set custom config
ETL_RABBITMQ_HOST=localhost ETL_SCHEMA_PATH=./test-schema.yaml uv run python -m worker
```

---

## Project Structure

```
etl/
├── __init__.py             # Package marker
├── __main__.py             # Entry point for `python -m worker`
├── config.py               # Environment configuration (pydantic-settings)
├── worker.py               # ETLWorker class, RabbitMQ consume/publish loop
├── transform.py            # Core ETL: validation, coercion, field mapping
├── schema.py               # Schema loading (ETLSchema, FieldDef dataclasses)
├── envelope.py             # Message envelope build/parse helpers
├── health.py               # HTTP health check server for Kubernetes probes
├── test_transform.py       # Unit tests for transform pipeline
├── configmap-etl-schema.yaml  # K8s ConfigMap with field definitions
├── pyproject.toml          # Package dependencies
├── Containerfile           # Container build instructions
└── docs/
    ├── developer-guide.md  # This file
    ├── schema-reference.md # Schema format specification
    └── troubleshooting.md  # Common errors and solutions
```

### Module Responsibilities

| Module | Responsibility |
|--------|----------------|
| `config.py` | Load environment variables with `ETL_` prefix |
| `schema.py` | Parse schema YAML, build lookup structures |
| `transform.py` | Validate, coerce, transform raw payloads |
| `envelope.py` | Build/parse message envelopes for RabbitMQ |
| `health.py` | HTTP health endpoints (`/healthz`, `/readyz`) for Kubernetes |
| `worker.py` | RabbitMQ connection, message routing, error handling |

---

## Code Conventions

### Type Hints

Always use type hints with modern syntax:

```python
from __future__ import annotations

def process(data: dict, required: bool = False) -> str | None:
    ...
```

### Data Structures

- **Immutable containers**: `@dataclass(frozen=True)`
- **Mutable with init logic**: `@dataclass` with `__post_init__`
- **Environment config**: `pydantic.BaseSettings`

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class FieldDef:
    source_key: str
    db_column: str | None
    type: str = "string"
```

### Naming

- `snake_case` for functions, variables, modules
- `PascalCase` for classes
- `_prefixed` for private helpers

### Imports

Group in order: stdlib, third-party, local

```python
import json
import uuid
from datetime import datetime

import pika
import yaml

from .config import Settings
from .schema import ETLSchema
```

### Error Classes

Include machine-readable code and human-readable message:

```python
class TransformError(Exception):
    def __init__(self, code: str, message: str, missing_fields: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.missing_fields = missing_fields or []

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, ...}
```

---

## Adding New Field Mappings

Edit `configmap-etl-schema.yaml` to add field mappings. No code changes required.

### Example: Add a New Required Field

```yaml
fields:
  # ... existing fields ...

  - source_key: budget_code
    db_column: budget_code
    type: string
    required: true
```

### Example: Add a Field with Transform

```yaml
- source_key: manager_name
  db_column: manager_first
  type: string
  required: false
  transform: split_name_first

- source_key: manager_name
  db_column: manager_last
  type: string
  required: false
  transform: split_name_last
```

---

## Adding New Transforms

Transforms modify coerced values. Add to `transform.py`:

### 1. Create the Transform Function

```python
def _normalize_phone(phone: str) -> str:
    """Strip non-digits, format as (xxx) xxx-xxxx."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return phone  # Return original if can't normalize
```

### 2. Register in TRANSFORMS Dict

```python
TRANSFORMS = {
    "split_name_first": _split_name_first,
    "split_name_last": _split_name_last,
    "normalize_phone": _normalize_phone,  # Add here
}
```

### 3. Use in Schema

```yaml
- source_key: phone_number
  db_column: phone
  type: string
  transform: normalize_phone
```

### 4. Add Tests

```python
class TestPhoneTransform:
    def test_normalizes_10_digit_phone(self):
        payload = {**SAMPLE_PAYLOAD, "phone_number": "5551234567"}
        result = transform(SCHEMA, payload)
        assert result["db_columns"]["phone"] == "(555) 123-4567"
```

---

## Adding New Field Generators

Generators create system fields not present in the source data. Add to `transform.py`:

### 1. Create the Generator Function

Generators receive the current `db_row` dict and return a value:

```python
def _generate_request_hash(db_row: dict) -> str:
    """Generate a hash of key request fields for deduplication."""
    key_fields = f"{db_row.get('company_name', '')}-{db_row.get('project_name', '')}"
    return hashlib.md5(key_fields.encode()).hexdigest()[:12]
```

### 2. Register in GENERATORS Dict

```python
GENERATORS = {
    "uuid4": lambda _row: _generate_uuid4(),
    "short_id": lambda _row: _generate_short_id(),
    "derive_cluster_name": _derive_cluster_name,
    "static": None,  # handled separately
    "request_hash": _generate_request_hash,  # Add here
}
```

### 3. Use in Schema

```yaml
generated_fields:
  - db_column: request_hash
    generator: request_hash
```

---

## Adding New Type Coercers

Type coercers convert raw values to typed values. Add to `transform.py`:

### 1. Create the Coercer Function

```python
def _coerce_url(val: Any) -> str:
    """Validate and normalize URL."""
    s = _coerce_string(val)
    if s and not s.startswith(("http://", "https://")):
        raise TransformError("INVALID_URL", f"URL must start with http:// or https://: '{s}'")
    return s
```

### 2. Register in COERCERS Dict

```python
COERCERS = {
    "string": _coerce_string,
    "int": _coerce_int,
    "float": _coerce_float,
    "bool": _coerce_bool,
    "datetime": _coerce_datetime,
    "email": _coerce_email,
    "url": _coerce_url,  # Add here
}
```

### 3. Use in Schema

```yaml
- source_key: project_url
  db_column: project_url
  type: url
  required: false
```

---

## Testing Patterns

### Test File Organization

Tests are organized by feature area:

```python
class TestTransformHappyPath:
    """Valid payload processing."""

class TestAutoProvisionPolicy:
    """Standard config detection."""

class TestValidationErrors:
    """Missing/malformed field handling."""

class TestUnknownFields:
    """Extras capture."""
```

### Using the Sample Payload

Start from `SAMPLE_PAYLOAD` and override specific fields:

```python
def test_custom_cluster_size(self):
    payload = {**SAMPLE_PAYLOAD, "cluster_size": "Large"}
    result = transform(SCHEMA, payload)
    assert result["db_columns"]["cluster_size"] == "Large"
```

### Testing Error Conditions

Use `pytest.raises` with assertion on error attributes:

```python
def test_missing_required_field_raises(self):
    payload = {**SAMPLE_PAYLOAD}
    del payload["company_name"]
    with pytest.raises(TransformError) as exc_info:
        transform(SCHEMA, payload)
    assert exc_info.value.code == "MISSING_REQUIRED_FIELD"
    assert "company_name" in exc_info.value.missing_fields
```

### Schema Loading in Tests

The test file extracts the inner YAML from the ConfigMap wrapper:

```python
def _load_test_schema():
    """Parse just the schema.yaml content from the ConfigMap."""
    import yaml
    raw = yaml.safe_load(SCHEMA_PATH.read_text())
    inner_yaml = raw.get("data", {}).get("schema.yaml", "")
    tmp = Path("/tmp/test-schema.yaml")
    tmp.write_text(inner_yaml)
    return load_schema(tmp)
```

---

## Running Tests

```bash
# All tests
uv run pytest test_transform.py -v

# Specific test class
uv run pytest test_transform.py::TestTransformHappyPath -v

# Specific test
uv run pytest test_transform.py::TestTransformHappyPath::test_produces_required_db_columns -v

# With coverage report
uv run pytest test_transform.py --cov=. --cov-report=html
open htmlcov/index.html
```

---

## Building the Container

From the `workers/` root directory:

```bash
podman build -f etl/Containerfile -t worker-etl:latest .

# Test locally
podman run --rm \
  -e ETL_RABBITMQ_HOST=host.containers.internal \
  -v ./etl/configmap-etl-schema.yaml:/etc/etl-schema/schema.yaml:ro \
  worker-etl:latest
```

---

## Debugging Tips

### Inspect Raw Messages

Use RabbitMQ Management UI at `http://localhost:15672` (guest/guest) to:
- View queue depths
- Publish test messages
- Inspect dead-lettered messages in `intake.raw.failed`

### Enable Debug Logging

```bash
PYTHONPATH=. python -c "
import logging
logging.basicConfig(level=logging.DEBUG)
from worker import main
main()
"
```

### Test Transform in Isolation

```python
from schema import load_schema
from transform import transform

schema = load_schema("/tmp/test-schema.yaml")
result = transform(schema, {"company_name": "Test", ...})
print(result)
```

---

## Related Documentation

- [Schema Reference](./schema-reference.md) - Schema format specification
- [Troubleshooting](./troubleshooting.md) - Common errors and solutions
- [Parent: Contributing](../../CONTRIBUTING.md) - PR process and guidelines
