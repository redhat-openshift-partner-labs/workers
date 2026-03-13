# ETL Worker Bootstrap - Engineering Journal

**Date:** March 12, 2026

---

## The Problem

The OpenShift Partner Labs pipeline needed an ETL worker to bridge Google Sheets intake with downstream processing. Raw payloads from AppScript arrive via RabbitMQ and need validation, type coercion, field mapping, and routing to either `intake.normalized` (success) or `intake.raw.failed` (errors). The CLAUDE.md documentation existed but was a template with incorrect tech stack references (Nuxt/Vue) — it needed a complete rewrite alongside the worker implementation.

**Stakeholders:** Platform team, downstream workers depending on normalized schema
**Success Criteria:** Working transform pipeline with tests, proper CLAUDE.md documentation, clean commit history

---

## SESSION 1: False Start and Course Correction

### Initial Approach

The first session began with exploring the project structure to understand what existed. I discovered the CLAUDE.md was a generic template with several problems:

| My Assumption | Reality |
|---------------|---------|
| CLAUDE.md would have project-specific info | Template with wrong tech stack (Nuxt 4.3.1, Vue, Prisma) |
| Schema would be hardcoded | Schema-driven design via YAML ConfigMap |
| Simple field mapping | Complex transforms: name splitting, email validation, auto-provision policy |

### The Pivot

The user interrupted the first session — likely because I was exploring too broadly without making progress. This was a signal to be more focused and action-oriented.

### The Lesson from Session 1

When updating documentation, don't just explore — build a concrete plan quickly and get user buy-in before deep-diving into implementation.

---

## SESSION 2: Complete Implementation

### Documentation-First Approach

The second session was more structured. After understanding the codebase, I created a plan showing exactly what would change in CLAUDE.md:

- **Removed:** Database/Prisma/SQLite references, UX developer role, Component Patterns, Styling, Internationalization
- **Added:** Worker purpose with message flow diagram, correct tech stack, worker contract (stateless, idempotent, scalable), actual commands and file structure

### Implementing the Transform Pipeline

The core transform module (`transform.py`) handles:
1. **Schema validation** — Required fields checked against YAML definitions
2. **Type coercion** — String/int/float/bool/datetime/email with structured errors
3. **Field mapping** — Source keys to database columns via schema
4. **Name splitting** — `primary_contact_name` maps to TWO columns (`primary_first`, `primary_last`)
5. **Auto-provision policy** — Evaluates if request qualifies for automatic provisioning

Key pattern in the coercion layer:

```python
COERCERS = {
    "string": _coerce_string,
    "int": _coerce_int,
    "float": _coerce_float,
    "bool": _coerce_bool,
    "datetime": _coerce_datetime,
    "email": _coerce_email,
}
```

### Structured Commit Strategy

The user wanted clean, incremental commits. I organized the work into logical units:

```
39f594d docs: add comprehensive CLAUDE.md for ETL worker
13ae135 chore: add project dependencies
6958879 feat: add ETL worker implementation
4c12a9a test: add transform pipeline tests
1386fd9 chore: add k8s schema configmap and containerfile
```

This ordering tells a story: documentation first (understanding), then dependencies, then implementation, tests, and finally deployment artifacts.

---

## WHAT I BUILT (AND DIDN'T BUILD)

**Built:**
- Complete ETL worker with RabbitMQ consumer/publisher
- Schema-driven field mapping via YAML ConfigMap
- Structured error handling with machine-readable codes
- Message envelope pattern for distributed tracing
- Comprehensive test suite with pytest
- Production-ready CLAUDE.md documentation
- Containerfile for deployment

**Deliberately Did NOT Build:**
- Database connectivity — ETL worker only transforms; downstream workers persist
- Retry logic with exponential backoff — Failed messages route to dead-letter queue instead
- Complex logging aggregation — Basic structured logging, observability handled at platform level

---

## TECHNICAL DECISIONS

| Decision | Context | Options Considered | Choice | Rationale |
|----------|---------|-------------------|--------|-----------|
| Schema in YAML ConfigMap | Field mappings change independent of code | Hardcoded mapping, JSON file, YAML ConfigMap | YAML ConfigMap | K8s-native, restart-only deployment, version-controlled |
| Error routing vs retry | Poison messages could block queue | Infinite retry, DLQ, error routing | Error routing to `intake.raw.failed` | Prevents blocking, enables manual inspection |
| Prefetch = 1 | Processing speed vs ordering guarantees | Higher prefetch, batching | Single message | Simplicity, correct ordering, scale via replicas |
| Frozen dataclasses | Schema definitions are immutable | Regular dataclass, Pydantic models | `@dataclass(frozen=True)` | Immutability enforced, no Pydantic overhead for internal types |

---

## TECHNICAL PATTERNS WORTH REMEMBERING

1. **Message Envelope Pattern** — Every message includes `event_type`, `event_id`, `correlation_id`, `causation_id`. This enables distributed tracing across the pipeline without coupling to specific observability tools.

2. **Schema-Driven Transforms** — Define field behaviors in YAML, not code. Allows non-developers to understand and modify field mappings. Example field definition:

```yaml
primary_contact_email:
  source_key: primaryContactEmail
  db_column: primary_email
  type: email
  required: true
```

3. **Structured TransformError** — Errors carry machine-readable `code` plus human-readable `message`. This enables downstream automation (retry certain codes, alert on others).

---

## FILES CHANGED

**New files:**
```
config.py                   — pydantic-settings config with ETL_* env vars
schema.py                   — YAML schema loading with FieldDef/ETLSchema dataclasses
envelope.py                 — Message envelope build/parse helpers
transform.py                — Core ETL: validation, coercion, field mapping
worker.py                   — RabbitMQ consumer with graceful shutdown
test_transform.py           — Unit tests for transform pipeline
configmap-etl-schema.yaml   — K8s ConfigMap with field definitions
pyproject.toml              — Package dependencies
Containerfile               — Container build instructions
CLAUDE.md                   — Complete rewrite with accurate documentation
```

---

## TESTING

**Unit tests:** 208 lines in `test_transform.py`
- `TestTransformHappyPath` — Valid payload processing
- `TestAutoProvisionPolicy` — Standard config detection
- `TestValidationErrors` — Missing/malformed field handling
- `TestUnknownFields` — Extras capture for undefined fields

**Manual testing:** Transform function tested with `SAMPLE_PAYLOAD` fixture
**Test coverage:** Not measured in session, but tests cover core transform paths

---

## DEPENDENCIES

**Added:**
- `pika>=1.3.2` — RabbitMQ client
- `pydantic>=2.7.0` — Validation and type coercion
- `pyyaml>=6.0` — Parse ConfigMap schema
- `pydantic-settings>=2.3.0` — Env-based config

**Dev dependencies:**
- `pytest>=8.0`
- `pytest-cov>=5.0`

---

## ERROR HANDLING

- **Failure modes:** Schema validation, type coercion, malformed emails, missing required fields
- **Recovery:** Failed messages routed to `intake.raw.failed` (not redelivered)
- **Error structure:** Machine-readable codes (`MISSING_REQUIRED_FIELD`, `MALFORMED_EMAIL`, `TYPE_COERCION_FAILED`)
- **Retry logic:** None — deliberate choice to avoid infinite loops on bad data

---

## API/INTERFACE QUICK REFERENCE

**Message Flow:**
```
intake.raw → [ETL Worker] → intake.normalized (success)
                         → intake.raw.failed (errors)
```

**Environment Variables:**
| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ETL_RABBITMQ_HOST` | no | `localhost` | RabbitMQ hostname |
| `ETL_RABBITMQ_PORT` | no | `5672` | RabbitMQ port |
| `ETL_RABBITMQ_USER` | no | `guest` | RabbitMQ username |
| `ETL_RABBITMQ_PASS` | no | `guest` | RabbitMQ password |
| `ETL_SCHEMA_PATH` | no | `/etc/etl-schema/schema.yaml` | Path to schema YAML |
| `ETL_PREFETCH_COUNT` | no | `1` | Messages to prefetch |

---

## TECH DEBT INCURRED

| Debt | Reason | Remediation |
|------|--------|-------------|
| Source files in root `etl/` vs `src/` | Rapid iteration, Containerfile expects `src/` | Align directory structure before production |
| No integration tests with RabbitMQ | Unit tests sufficient for transform logic | Add testcontainers-based integration tests |
| Schema path hardcoded for local dev | ConfigMap path differs from local | Add schema path auto-detection or fixture helper |

---

## NEXT STEPS (NOT THIS SESSION)

- Commit remaining parent directory files (commons-python, schemas, docs)
- Add integration tests with RabbitMQ testcontainers
- Align `src/` directory structure with Containerfile
- Set up CI/CD pipeline for automated testing

---

## COMMITS

```
1386fd9 chore: add k8s schema configmap and containerfile
4c12a9a test: add transform pipeline tests
6958879 feat: add ETL worker implementation
13ae135 chore: add project dependencies
39f594d docs: add comprehensive CLAUDE.md for ETL worker
```

---

## THE RETROSPECTIVE

This session was a clean bootstrap of a new microservice from template to production-ready. The key insight was recognizing that the existing CLAUDE.md template was actively harmful — it described a completely different tech stack and would mislead any developer (human or AI) reading it. Documentation-first development paid off: writing the CLAUDE.md forced clarity about what the worker actually does before writing code.

The structured commit strategy was valuable. Rather than one massive commit with everything, breaking the work into logical units (docs → deps → implementation → tests → k8s) makes the history readable and rollback-safe. Each commit tells part of the story.

If I were doing this again, I'd spend less time in the first session exploring and more time presenting a concrete plan to the user. The interrupt was a signal that I was spinning wheels. The second session was more effective because it was structured: understand, plan, execute, commit.

The biggest takeaway: schema-driven design is worth the upfront investment. Putting field mappings in YAML instead of code means the schema becomes documentation, configuration, and behavior all in one place. When the next field needs to be added, it's a ConfigMap change, not a code deployment.
