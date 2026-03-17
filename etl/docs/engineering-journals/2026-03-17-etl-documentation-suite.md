# ETL Worker Documentation Suite - Engineering Journal

**Date:** March 17, 2026

---

## The Request

The ETL worker had functional code but lacked proper documentation. The existing `CLAUDE.md` served as AI context, not human-readable documentation. The user had a detailed plan ready — a documentation suite consisting of a main README and three supplemental guides (developer, troubleshooting, schema reference).

**Stakeholders:** Developers onboarding to the project, operators deploying/debugging the worker
**Success Criteria:** Complete documentation that a new developer could follow without additional context

---

## SESSION 1: DOCUMENTATION IMPLEMENTATION

### Following the Plan

The user came in with a fully-formed documentation plan from a previous session. This was refreshingly clear — no ambiguity about what was needed. The plan specified:

1. `etl/docs/schema-reference.md` — foundational, referenced by others
2. `etl/docs/developer-guide.md` — depends on schema reference
3. `etl/docs/troubleshooting.md` — standalone
4. `etl/README.md` — ties everything together

### Reading the Source Before Writing

Before writing a single line of documentation, I read through all the source files to ensure accuracy:

- `config.py` — environment variables and their defaults
- `transform.py` — the actual transform pipeline, coercers, transforms, generators
- `schema.py` — schema loading and data structures
- `worker.py` — RabbitMQ consumer/producer, message routing
- `envelope.py` — message envelope construction
- `configmap-etl-schema.yaml` — the actual schema definition
- `test_transform.py` — test patterns and fixtures

This was time well spent. The documentation needed to be accurate, not aspirational.

### The Implementation

I created the four files in the planned order. Key decisions:

**Schema Reference** — Made this the most technical document. Included complete attribute tables, all supported types/transforms/generators, and crucially, the auto-provision policy evaluation logic. The three conditions (standard criteria fields, complexity keywords, note length) were explicitly documented.

**Developer Guide** — Focused on extension points: how to add new field mappings (schema-only), new transforms (code + schema), new generators (code + schema), and new type coercers (code + schema). Included complete code examples.

**Troubleshooting** — Organized by error code (`MISSING_REQUIRED_FIELD`, `MALFORMED_EMAIL`, etc.) with solutions. Added sections on RabbitMQ connection issues, schema loading problems, and container startup failures.

**README** — The hub document. Two Mermaid diagrams (message flow, transform pipeline), configuration table, message envelope documentation with tracing explanation, and links to all supplemental guides plus parent repo docs.

---

## SESSION 2: SCHEMA VALIDATION

### The Payload/Schema Comparison

The user asked whether `tmp/payload.example` (real AppScript webhook output) and `tmp/schema.example` (Prisma DB schema) required any ETL changes.

This was a valuable exercise. I compared:

| DB Column (Prisma) | ETL Mapping | Status |
|-------------------|-------------|--------|
| All required columns | Mapped or generated | OK |
| `company_id` | Not mapped | Intentionally — resolved by Scribe |
| `completed_at` | Not mapped | Intentionally — set on state change |
| `created_at`/`updated_at` | Not mapped | DB handles with defaults |

The answer: **No changes required.** The ETL schema was already aligned with both the incoming payload structure and the downstream database schema.

### Finding the Auto-Provision Code

User asked: "where is auto-provision implemented?"

Pointed to `transform.py:161-183`, the `_evaluate_standard_config()` function. Three conditions:
1. All `is_standard_criteria` fields must have values in their `standard_values` list
2. Description must not contain complexity keywords
3. Note field must be empty or ≤10 characters

### Confirming Documentation Coverage

User followed up: "is this noted in the docs?"

Yes — `docs/schema-reference.md` lines 175-202 cover the Auto-Provision Policy section with all three conditions and the complexity keywords list. The README also mentions it in the transform pipeline steps.

---

## SESSION 3: INCREMENTAL COMMITS

### Organizing the Chaos

The working tree had accumulated changes across multiple files:
- New ETL docs (already committed in previous session)
- ETL package setup (`__init__.py`, `pyproject.toml`, `uv.lock`)
- Test import fixes
- Parent repo documentation updates (README, CONTRIBUTING, CLAUDE.md)
- New architecture documentation
- Naming consistency (`dayone` → `day-one`)

I created 10 focused commits:

1. **`572c5a8`** — `__init__.py` package marker
2. **`28fc26a`** — Test import fixes (relative imports, correct schema path)
3. **`b329db4`** — uv workspace configuration
4. **`5dc7776`** — CLAUDE.md: dayone → day-one
5. **`287b89d`** — CONTRIBUTING.md: table formatting, DLQ conventions
6. **`f54ce50`** — schema-evolution.md: semantic versioning clarification
7. **`2712952`** — NEW: architecture.md with component map
8. **`3bc8ffa`** — diagrams.md: scribe-centric architecture, state machine
9. **`4be0a57`** — README.md: scribe-centric message flow
10. **`d86c9b3`** — NEW: REFERENCE.md (queue-schemas-v3)

Each commit is atomic and rollback-friendly.

---

## WHAT I BUILT (AND DIDN'T BUILD)

**Built:**
- `etl/README.md` — Main documentation entry point with Mermaid diagrams
- `etl/docs/schema-reference.md` — Complete schema YAML specification
- `etl/docs/developer-guide.md` — Extension guide with code examples
- `etl/docs/troubleshooting.md` — Error codes and debugging guide
- Committed accumulated parent repo documentation updates

**Deliberately Did NOT Build:**
- Integration test fixtures — documentation only, no test changes
- Schema changes — validated existing schema covers all use cases
- Code refactoring — documentation shouldn't change behavior

---

## TECHNICAL DECISIONS

| Decision | Context | Options Considered | Choice | Rationale |
|----------|---------|-------------------|--------|-----------|
| Separate docs vs inline README | README was getting long | All-in-one, separate guides | Separate guides | README stays scannable, details in topic-specific docs |
| Document auto-provision in schema-reference | Logic is schema-driven | README, transform.py docstring, schema-reference | schema-reference | It's configured via schema, so belongs there |
| Include full error code reference | Troubleshooting needs to be actionable | Just link to code, full docs, examples | Full docs with solutions | Operator shouldn't need to read source code |

---

## TECHNICAL PATTERNS WORTH REMEMBERING

1. **Schema-driven ETL** — Field mappings in YAML, not code. Restart to pick up changes. This makes the documentation easier too — just document the schema format.

2. **Structured errors with codes** — `TransformError` has both `code` (machine-readable) and `message` (human-readable). Makes documentation cleaner — error codes are stable identifiers.

3. **Auto-provision as policy evaluation** — Three conditions checked at transform time, result stored in output. Downstream workers don't re-evaluate — they trust `is_standard_config`.

---

## FILES CHANGED

**New files:**
```
etl/README.md — Main documentation with diagrams
etl/docs/schema-reference.md — Schema YAML specification
etl/docs/developer-guide.md — Extension patterns
etl/docs/troubleshooting.md — Error codes and debugging
etl/__init__.py — Package marker
docs/architecture.md — System component map
REFERENCE.md — Queue names and schemas (v3)
```

**Modified files:**
```
etl/pyproject.toml — uv workspace configuration
etl/uv.lock — Updated lockfile
etl/test_transform.py — Relative imports, correct schema path
CLAUDE.md — dayone → day-one
CONTRIBUTING.md — Table formatting, DLQ conventions
README.md — Scribe-centric message flow
docs/diagrams.md — State machine, updated architecture
docs/schema-evolution.md — Semantic versioning clarification
```

---

## TESTING

**Unit tests:** No changes to test logic
**Integration tests:** None
**Manual testing:** Verified Mermaid diagrams render (mental model check)
**Test coverage:** Not measured this session

The test import fix (`28fc26a`) was necessary — tests were pointing to `src.schema` and `src.transform` but the module structure is flat.

---

## OBSERVABILITY

The troubleshooting guide documents:
- **Logging:** Worker logs at INFO level, errors at WARNING/ERROR
- **Tracing:** `correlation_id` preserved across the entire pipeline, `causation_id` links parent→child messages
- **Debugging:** RabbitMQ Management UI for queue inspection, local transform testing patterns

---

## ERROR HANDLING

Documented all transform error codes:

| Code | When | Solution |
|------|------|----------|
| `MISSING_REQUIRED_FIELD` | Required field empty/missing | Check source data, field names |
| `MALFORMED_EMAIL` | Email format validation failed | Fix email format |
| `TYPE_COERCION_FAILED` | Can't convert to expected type | Check schema type, source data |
| `INVALID_DATETIME` | Can't parse datetime | Use ISO 8601 format |
| `UNEXPECTED_ERROR` | Unhandled exception | Check logs, report bug |

---

## API/INTERFACE QUICK REFERENCE

**Environment Variables:**
| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ETL_RABBITMQ_HOST` | No | `localhost` | RabbitMQ hostname |
| `ETL_RABBITMQ_PORT` | No | `5672` | RabbitMQ port |
| `ETL_CONSUME_QUEUE` | No | `intake.raw` | Input queue |
| `ETL_PUBLISH_QUEUE` | No | `intake.normalized` | Output queue |
| `ETL_FAILED_QUEUE` | No | `intake.raw.failed` | Error queue |
| `ETL_SCHEMA_PATH` | No | `/etc/etl-schema/schema.yaml` | Schema location |

---

## PRE-EXISTING ISSUES NOTED

| Issue | Severity | Notes |
|-------|----------|-------|
| Test schema path assumption | Low | Tests expect ConfigMap at `etl/configmap-etl-schema.yaml` — works but fragile |
| No `__main__.py` | Low | `python -m worker` works but could be cleaner with proper entry point |

---

## TECH DEBT INCURRED

| Debt | Reason | Remediation |
|------|--------|-------------|
| None | Documentation-only session | N/A |

---

## NEXT STEPS (NOT THIS SESSION)

- Integration tests with actual RabbitMQ
- CI/CD pipeline for ETL worker
- Kubernetes deployment manifests in `etl/k8s/`
- Schema validation tooling (JSON Schema for payload validation)

---

## COMMITS

```
d86c9b3 docs: add queue names and message schemas reference
4be0a57 docs: update README with scribe-centric message flow
3bc8ffa docs: update diagrams with scribe-centric architecture
2712952 docs: add system architecture documentation
f54ce50 docs: clarify schema versioning with semantic versioning
287b89d docs: update CONTRIBUTING.md formatting and DLQ conventions
5dc7776 docs: update dayone references to day-one
b329db4 chore(etl): add uv workspace configuration
28fc26a fix(etl): update test imports to use relative paths
572c5a8 chore(etl): add __init__.py package marker
13ee246 docs(etl): add comprehensive documentation
```

---

## THE RETROSPECTIVE

This session was a study in following a good plan. The user came in with a clear documentation structure from a previous planning session, and I executed it. The value was in the details — reading every source file before documenting, ensuring error codes matched exactly, including complete examples.

The mid-session pivot to schema validation was valuable. Comparing the real payload example and Prisma schema against the ETL mappings confirmed the implementation was sound. No code changes needed — just documentation. That's a good sign for the original design.

The incremental commit exercise at the end was satisfying. Ten focused commits instead of one massive "documentation update" commit. Each one is comprehensible in isolation, and any can be reverted without affecting the others. This is how documentation work should be committed — atomic units of meaning.

Biggest takeaway: Documentation is most accurate when written by reading the code, not the comments. I found the auto-provision logic by reading `transform.py`, not by looking at docstrings. The three conditions (standard criteria, complexity keywords, note length) were all there in the code, clearly structured. The documentation just needed to surface that structure for humans.
