# OpenShift Partner Labs Workers

## Project Overview

Python monorepo for OpenShift Partner Labs worker services. Workers communicate via RabbitMQ using a standardized message envelope pattern for distributed tracing.

## Architecture

```
workers/
├── commons-python/     # Shared Python utilities (envelope, rabbitmq, config)
├── schemas/            # JSON Schema definitions (source of truth)
├── etl/                # ETL worker - intake data transformation
├── day-one/             # Day One worker - cluster initialization scripts
└── docs/               # Architectural documentation
```

### Message Flow

```
API → intake.raw → [ETL] → intake.normalized → [Provisioning] → lab.provision.*
                                                      ↓
                                              [Day-One] → lab.day1.*
                                                      ↓
                                              [Day-Two] → lab.day2.*
```

## Coding Conventions

### Python Standards
- **Version**: Python 3.12+
- **Type hints**: Required. Use `from __future__ import annotations` and `X | None` syntax
- **Style**: PEP 8 (snake_case functions/variables, PascalCase classes)
- **Imports**: Group as stdlib, third-party, local

### Data Structures
- `@dataclass(frozen=True)` for immutable containers
- `@dataclass` with `__post_init__` for mutable containers with initialization logic
- `pydantic.BaseSettings` for environment configuration

### Configuration
- All config via environment variables (12-factor)
- Worker-specific prefix: `{WORKER}_` (e.g., `ETL_RABBITMQ_HOST`)
- Use `pydantic-settings` for type-safe parsing

### Error Handling
- Structured exceptions with machine-readable `code` and human-readable `message`
- Failed messages route to dead-letter queue (`{queue}.dlq`), not retried infinitely
- Always ACK after processing

### Testing
- Framework: pytest
- Pattern: Test classes grouped by feature (`TestHappyPath`, `TestValidationErrors`)
- Fixtures for reusable setup
- Run: `pytest -v` or `pytest --cov=. --cov-report=term-missing`

## Worker Guidelines

### ETL Worker (`etl/`)
- **Purpose**: Validates and transforms raw Google Sheet payloads to canonical format
- **Queues**: `intake.raw` → `intake.normalized` (success) / `intake.raw.failed` (errors)
- **Schema**: YAML-driven field mappings in ConfigMap (`/etc/etl-schema/schema.yaml`)
- **See**: `etl/CLAUDE.md` for detailed implementation docs

### Day One Worker (`day-one/`)
- **Current state**: Operational scripts only (not a full worker yet)
- **Scripts**: `scripts/disable-insights.sh` - Disables Red Hat Insights in OpenShift

## Dependencies

### Core Stack
- `pika>=1.3.2` - RabbitMQ client
- `pydantic>=2.7.0` - Validation and serialization
- `pydantic-settings>=2.3.0` - Environment configuration
- `pyyaml>=6.0` - YAML parsing

### Development
- `pytest>=8.0` - Testing framework
- `pytest-cov>=5.0` - Coverage reporting

## Common Operations

### Local Development
```bash
# Install worker dependencies
cd etl && pip install -e '.[dev]'

# Run tests
pytest -v

# Start worker (requires RabbitMQ)
python -m worker
```

### Container Build
```bash
# Build from workers/ root
podman build -f etl/Containerfile -t worker-etl .
```

### Environment Variables (ETL example)
```bash
ETL_RABBITMQ_HOST=localhost
ETL_RABBITMQ_PORT=5672
ETL_CONSUME_QUEUE=intake.raw
ETL_PUBLISH_QUEUE=intake.normalized
ETL_SCHEMA_PATH=/etc/etl-schema/schema.yaml
```

## Message Envelope Pattern

All messages wrapped in standard envelope for tracing:
```json
{
  "event_type": "intake.normalized",
  "event_id": "uuid",
  "timestamp": "ISO8601",
  "source": "worker-etl",
  "correlation_id": "uuid",
  "causation_id": "uuid",
  "payload": { ... }
}
```

## Key Design Principles

1. **Schemas-first**: `schemas/` is the single source of truth
2. **Stateless workers**: No in-memory state between messages
3. **Idempotent processing**: Same message → same result
4. **Horizontal scaling**: Via replicas with `prefetch_count=1`
5. **Graceful shutdown**: Handle SIGTERM/SIGINT for Kubernetes
6. **Dead-letter routing**: Failed messages to DLQ, not retried forever

## Documentation

- `docs/deployment.md` - CI/CD pipeline, k8s manifests, ArgoCD
- `docs/schema-evolution.md` - Breaking change policy, versioning
- `docs/diagrams.md` - Architecture diagrams (Mermaid)
- `CONTRIBUTING.md` - Development setup, PR process
