# CLAUDE.md

This file provides context for AI assistants working on the ETL worker.

## Git Policy
- **NEVER push to remote repository** - User handles all pushes manually
- **DO make frequent incremental commits** - Small, focused commits for easy rollback
- **Commit after completing logical units of work** - Don't wait to be asked; commit when a feature, fix, or refactor is complete
- **Ask if uncertain** - If unclear whether work is "complete enough" to commit, ask first
- Use conventional commit messages (feat:, fix:, test:, docs:, refactor:, chore:)

## Role Context
- Expert Python developer
- Expert Microservices developer
- Expert Python test developer

## Development Approach
- TDD: Write tests with pytest first
- Create unit tests for transform logic, integration tests with RabbitMQ
- Use pytest fixtures for test setup
- Use mermaid for documentation diagrams

## Project Overview

The ETL worker validates and transforms raw Google Sheet payloads (from AppScript) into a canonical `intake.normalized` schema for downstream workers in the OpenShift Partner Labs pipeline.

**Message Flow:**
```
intake.raw → [ETL Worker] → intake.normalized (success)
                         → intake.raw.failed (errors)
```

**Tech Stack:**
- **Language**: Python 3.12
- **Message Broker**: RabbitMQ (pika client)
- **Validation**: Pydantic 2.x
- **Config**: pydantic-settings (env-based, 12-factor)
- **Schema**: YAML (loaded from ConfigMap in K8s)
- **Testing**: pytest, pytest-cov

**Worker Contract:**
- **Stateless**: No in-memory state between messages
- **Idempotent**: Same message processed twice produces same result
- **Scalable**: Horizontally via replicas (prefetch=1)
- **Graceful shutdown**: Handles SIGTERM/SIGINT

## Quick Reference

### Commands

```bash
# Install dependencies (from etl/ directory)
pip install -e '.[dev]'

# Run worker locally (requires RabbitMQ at localhost:5672)
python -m worker

# Run tests
pytest test_transform.py -v

# Run tests with coverage
pytest test_transform.py -v --cov=. --cov-report=term-missing

# Build container (from workers/ root directory)
podman build -f etl/Containerfile -t worker-etl .
```

### Key Directories

```
etl/
├── config.py                   # pydantic-settings config (ETL_* env vars)
├── worker.py                   # ETLWorker class, RabbitMQ consume/publish loop
├── transform.py                # Core ETL: validation, coercion, field mapping
├── schema.py                   # Schema loading (ETLSchema, FieldDef dataclasses)
├── envelope.py                 # Message envelope build/parse helpers
├── test_transform.py           # Unit tests for transform pipeline
├── configmap-etl-schema.yaml   # K8s ConfigMap with field definitions
├── pyproject.toml              # Package dependencies
└── Containerfile               # Container build instructions
```

## Architecture Decisions

### Schema-Driven Transformation
Field mappings, types, and transforms are defined in YAML (`configmap-etl-schema.yaml`), not hardcoded. This allows schema updates without code changes — just update the ConfigMap and restart.

### Message Envelope Pattern
All messages use a standard envelope with `event_type`, `event_id`, `correlation_id`, `causation_id`, and `payload`. This enables distributed tracing and message lineage tracking across workers.

### Error Handling Strategy
- Structured `TransformError` exceptions with machine-readable codes (`MISSING_REQUIRED_FIELD`, `MALFORMED_EMAIL`, etc.)
- Failed messages go to `intake.raw.failed` queue (not redelivered) to prevent poison message blocking
- Always ACK after processing — failures are routed, not retried infinitely

### Auto-Provision Policy
The transform evaluates whether a request qualifies for automatic provisioning based on:
- `is_standard_criteria` fields having values within `standard_values`
- Description not containing complexity keywords (GPU, custom, assistance, etc.)
- No substantial special requests in the notes field

## Code Conventions

### Type Hints
- Use `from __future__ import annotations` for modern syntax
- Full type hints on function signatures
- Use `X | None` instead of `Optional[X]`

### Data Structures
- `@dataclass(frozen=True)` for immutable data containers (FieldDef, GeneratedFieldDef)
- `@dataclass` for mutable containers with `__post_init__` logic (ETLSchema)
- Pydantic `BaseSettings` for environment configuration

### Naming
- `snake_case` for functions, variables, modules
- `PascalCase` for classes
- Private helpers prefixed with `_` (e.g., `_coerce_string`, `_split_name_first`)

### Imports
- Group: stdlib, third-party, local
- Use relative imports for local modules (`.config`, `.schema`, `.transform`)

### Error Classes
- Include `code` (machine-readable), `message` (human-readable)
- Provide `to_dict()` method for serialization

## Gotchas

- **Schema path**: In K8s, schema is mounted at `/etc/etl-schema/schema.yaml`. For local dev, tests extract the inner YAML from the ConfigMap wrapper in `configmap-etl-schema.yaml`.

- **File structure**: Source files are currently in the root `etl/` directory. The Containerfile expects `src/` — this may need alignment.

- **Name splitting**: `primary_contact_name` maps to TWO db_columns (`primary_first`, `primary_last`) via different transforms on the same source key.

- **Extras JSONB**: Fields with `db_column: null` go to the `extras` dict, except metadata fields (`timestamp`, `status`, `evaluated_on`, `email`) which are intentionally dropped.

## Testing

```bash
# Run all tests
pytest test_transform.py -v

# Run specific test class
pytest test_transform.py::TestTransformHappyPath -v

# Run with coverage
pytest test_transform.py --cov=. --cov-report=html
```

### Test Suite
- **Framework**: pytest
- **Tests**: `test_transform.py`
- **Pattern**: Test classes grouped by feature area:
  - `TestTransformHappyPath` — valid payload processing
  - `TestAutoProvisionPolicy` — standard config detection
  - `TestValidationErrors` — missing/malformed field handling
  - `TestUnknownFields` — extras capture

### Testing Guidelines
- Use `SAMPLE_PAYLOAD` as base, override specific fields for test cases
- Schema loaded from ConfigMap fixture with YAML wrapper extraction
- Test both success paths and structured error codes

## Dependencies

From `pyproject.toml`:
- `pika>=1.3.2` — RabbitMQ client
- `pydantic>=2.7.0` — Validation and type coercion
- `pyyaml>=6.0` — Parse ConfigMap schema
- `pydantic-settings>=2.3.0` — Env-based config

Dev dependencies:
- `pytest>=8.0`
- `pytest-cov>=5.0`

## Environment Variables

All variables use the `ETL_` prefix (configured in `Settings.model_config`):

| Variable | Default | Description |
|----------|---------|-------------|
| `ETL_RABBITMQ_HOST` | `localhost` | RabbitMQ hostname |
| `ETL_RABBITMQ_PORT` | `5672` | RabbitMQ port |
| `ETL_RABBITMQ_USER` | `guest` | RabbitMQ username |
| `ETL_RABBITMQ_PASS` | `guest` | RabbitMQ password |
| `ETL_RABBITMQ_VHOST` | `/` | RabbitMQ virtual host |
| `ETL_CONSUME_QUEUE` | `intake.raw` | Queue to consume from |
| `ETL_PUBLISH_QUEUE` | `intake.normalized` | Queue for successful transforms |
| `ETL_FAILED_QUEUE` | `intake.raw.failed` | Queue for failed messages |
| `ETL_SCHEMA_PATH` | `/etc/etl-schema/schema.yaml` | Path to schema YAML |
| `ETL_SOURCE_ID` | `worker-etl` | Worker identity in message envelopes |
| `ETL_PREFETCH_COUNT` | `1` | Messages to prefetch (1 = process one at a time) |
| `ETL_HEALTH_PORT` | `8080` | HTTP health check server port |
