# schemas/ — Language-Neutral Source of Truth

This directory contains JSON Schema definitions for the `MessageEnvelope` and all payload types used across workers. **This is the authority.** If a `commons-{language}` implementation disagrees with a schema here, the schema wins.

---

## Directory Layout

```
schemas/
├── envelope.schema.json          # MessageEnvelope wrapper
├── payloads/                     # One file per event type
│   ├── intake.raw.schema.json
│   ├── intake.normalized.schema.json
│   ├── intake.dispatch.provision.schema.json
│   └── ...
├── fixtures/                     # Test fixtures for contract tests
│   ├── valid/
│   │   ├── intake.raw.valid.json
│   │   └── ...
│   └── invalid/
│       ├── intake.raw.missing-field.json
│       └── ...
└── README.md
```

---

## Adding a New Payload Schema

1. **Create the schema file** in `schemas/payloads/` following the naming convention: `{domain}.{action}.schema.json` (e.g., `lab.provision.generate-manifests.schema.json`).

2. **Reference it in the envelope.** The envelope schema's `payload` field uses a discriminator (typically `event_type`) to select the correct payload schema. Add your new event type to the enum and the corresponding `$ref`.

3. **Add test fixtures.** Create at least one valid and one invalid fixture in `schemas/fixtures/`. These are used by contract tests.

4. **Update `commons-python`.** Add a Pydantic model for the new payload in `commons-python/`. It must serialize/deserialize identically to the JSON Schema definition.

5. **Update `commons-go`** (if Go workers consume this event type). Add a Go struct with matching JSON tags.

6. **Run contract tests locally:**
   ```bash
   make test-contracts
   ```

---

## Contract Tests

Contract tests verify that all `commons-{language}` implementations agree on serialization. They run automatically in CI whenever `schemas/` or any `commons-*/` directory changes.

### What they test

- **Fixture validation:** Every fixture in `schemas/fixtures/valid/` must pass schema validation. Every fixture in `schemas/fixtures/invalid/` must fail.
- **Round-trip serialization:** A message built by `commons-python` is serialized to JSON, then deserialized by `commons-go` (and vice versa). The result must match field-for-field.
- **Envelope integrity:** Metadata fields (correlation ID, timestamp, schema version, source worker) survive the round-trip without loss or mutation.

### Running locally

```bash
# Python-only validation (fast, no Go needed)
make test-schema-validate

# Full cross-language round-trip (requires Go 1.22+)
make test-contracts
```

---

## Schema Naming Convention

| Pattern | Example | Meaning |
|---|---|---|
| `{domain}.{action}.schema.json` | `intake.raw.schema.json` | A payload for the `intake.raw` event type |
| `{name}.v2.schema.json` | `intake.raw.v2.schema.json` | A breaking revision (see [schema evolution policy](../docs/schema-evolution.md)) |
| `envelope.schema.json` | — | The outer wrapper; all messages conform to this |
| `generic-task.schema.json` | — | A catch-all for simple task payloads |

---

## Validation Tooling

Workers can validate messages at runtime using `commons`:

```python
from commons.envelope import validate_message

# Returns (True, None) or (False, error_detail)
is_valid, error = validate_message(raw_json)
```

The validation function loads the appropriate schema based on the `event_type` field in the envelope. Schema files are either bundled with the `commons` package or mounted as a ConfigMap in Kubernetes (see `k8s/configmap-*-schema.yaml` in worker directories).
