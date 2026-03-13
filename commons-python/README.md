# commons — Shared Python Library

The `commons` package provides the shared building blocks used by all Python workers in this monorepo. It implements the contracts defined in [`schemas/`](../schemas/README.md).

---

## Installation

From any worker directory:

```bash
pip install -e '../commons-python'
```

Or as part of the worker's dev setup:

```bash
pip install -e '.[dev]' -e '../commons-python'
```

---

## Modules

### `envelope.py` — MessageEnvelope

Build, parse, and validate the standard message envelope that wraps all payloads on RabbitMQ.

```python
from commons.envelope import build_envelope, parse_envelope, validate_message

# Build an envelope around a payload
envelope = build_envelope(
    event_type="intake.raw",
    payload={"source": "api", "data": {...}},
    source_worker="worker-etl",
    correlation_id="abc-123",         # optional; auto-generated if omitted
)

# Serialize to JSON bytes for publishing
raw = envelope.to_json()

# Parse an incoming message
envelope = parse_envelope(raw)
print(envelope.event_type)            # "intake.raw"
print(envelope.payload)               # dict
print(envelope.metadata.correlation_id)

# Validate against JSON Schema without parsing into a model
is_valid, error = validate_message(raw)
```

### `rabbitmq.py` — Connection & Channel Helpers

Manage RabbitMQ connections with automatic reconnect and standardized consume/publish patterns.

```python
from commons.rabbitmq import RabbitMQConnection

conn = RabbitMQConnection(
    host="localhost",
    port=5672,
    username="guest",
    password="guest",
)

# Publish
conn.publish(queue="intake.raw", body=envelope.to_json())

# Consume with automatic ack/nack and DLQ routing
def handler(envelope):
    # process...
    return  # implicit ack on success; exceptions trigger nack + DLQ after retries

conn.consume(queue="intake.raw", handler=handler)
```

**Reconnect behavior:** On connection loss, the helper retries with exponential backoff (default: 1s → 2s → 4s → ... → 60s cap). This is configurable via constructor parameters.

**Dead-letter queue convention:** Every queue `{name}` has a corresponding DLQ `{name}.dlq`. Messages that fail after `max_retries` (default: 3) are routed there with the error detail attached to the envelope's `error` field.

### `config_base.py` — Base Settings

A `pydantic-settings` base class with shared environment variable patterns.

```python
from commons.config_base import BaseWorkerSettings

class EtlConfig(BaseWorkerSettings):
    # Inherited: RABBITMQ_HOST, RABBITMQ_PORT, RABBITMQ_USER, RABBITMQ_PASS, LOG_LEVEL
    gpu_field_enabled: bool = False
    schema_map_path: str = "/app/schemas"
```

All settings are loaded from environment variables (uppercased, underscore-delimited). See each field's default in the base class source.

---

## Package Naming

- **Directory:** `commons-python/`
- **Package name** (in `pyproject.toml`): `commons`
- **Import path:** `commons`

```python
# Correct
from commons.envelope import build_envelope

# Wrong — this is the directory name, not the package
# from commons_python.envelope import build_envelope
```

---

## Development

```bash
cd commons-python
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest tests/ -v
```

Changes to `commons-python/` trigger CI for **all** Python workers. Keep changes backward-compatible whenever possible. See [`docs/schema-evolution.md`](../docs/schema-evolution.md) for the policy on breaking changes.
