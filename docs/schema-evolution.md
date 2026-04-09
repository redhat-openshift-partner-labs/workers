# Schema Evolution Policy

---

## Principles

1. **`schemas/` is the authority.** Language-specific implementations in `commons-{language}` must conform. Never the reverse.
2. **Additive by default.** Prefer backward-compatible changes that don't break existing consumers.
3. **Breaking changes are versioned and coordinated.** They require a migration plan and cannot be merged without all affected workers updating in the same PR (or a coordinated rollout).

---

## What Counts as Additive (Non-Breaking)

These changes are safe to merge without a version bump:

- Adding a new **optional** field to an existing payload schema.
- Adding a new payload schema file in `schemas/payloads/`.
- Adding a new enum value **if consumers use `additionalProperties: true`** or ignore unknown values.
- Relaxing a constraint (e.g., removing `minLength`, making a required field optional).

**Workflow:** Standard PR into develop. All worker CIs will run (because `schemas/**` is in every workflow's path filter). If tests pass, the change is safe.

---

## What Counts as Breaking

These changes require the versioned migration process below:

- Removing or renaming a field.
- Changing a field's type.
- Adding a new **required** field to an existing schema.
- Tightening a constraint (e.g., adding `maxLength`, making an optional field required).
- Changing the envelope structure itself.

---

## Versioning Convention

Schemas use **semantic versioning** (`major.minor.patch`):

- **Minor bump** — backward-compatible changes (adding optional fields). No migration needed.
- **Major bump** — breaking changes (removing/renaming required fields, type changes). Requires the migration playbook below.
- **Patch bump** — documentation-only changes, description clarifications. No runtime impact.

The `version` field in the **MessageEnvelope** carries the **envelope format version** (currently always `"1.0.0"`). It is not the payload schema version. Payload schema versions are tracked by the **schema filename** — a breaking revision adds a `.v2` suffix to the file, and consumers determine which schema applies from `event_type`.

Each schema's `$id` is a file-relative path matching its location under `schemas/`:

```
payloads/intake.raw.schema.json
payloads/intake.raw.v2.schema.json   ← breaking revision
```

When a breaking change is needed, the new schema file coexists alongside the original:

```
schemas/payloads/
├── intake.raw.schema.json        # v1 (current, event_type: "intake.raw")
└── intake.raw.v2.schema.json     # v2 (breaking revision)
```

> **Why not subdirectories (`v1/`, `v2/`)?** Most schemas evolve independently.
> A single schema getting a v2 shouldn't force a directory restructure for all others.

---

## Breaking Change Playbook

### 1. Draft the new schema

Create the new versioned schema file (e.g., `intake.raw.v2.schema.json`) alongside the existing one. Do not modify the original yet.

### 2. Update `commons-{language}`

Add support for both the old and new schema versions. The envelope builder should be able to produce either version. The parser should accept both.

### 3. Update consumers first

Workers that **consume** the affected message type must be updated to handle both versions before any producer starts emitting the new version. This is the critical ordering constraint.

### 4. Update producers

Once all consumers can handle the new version, update the producing worker to emit the new version.

### 5. Deprecate the old schema

After a soak period (at minimum one full release cycle), remove the old schema and the dual-version handling from `commons-{language}`.

### 6. Coordinate via PR

For changes that touch multiple workers, use a single atomic PR where possible. If the change is too large for one PR, document the rollout order in the PR description and use feature flags or version checks to gate behavior.

---

## Runtime Validation

Workers **should** validate incoming messages against the JSON Schema at runtime using the helpers in `commons`. This catches:

- Producers emitting malformed messages.
- Schema drift between what a producer thinks it's sending and what the consumer expects.

Messages that fail validation are routed to the dead-letter queue with the validation error attached to the envelope's `error` field.

---

## Contract Tests

Cross-language contract tests live alongside the schemas and are run in CI whenever `schemas/` or any `commons-{language}/` directory changes. See [`schemas/README.md`](../schemas/README.md) for how to run them.

The tests verify:
- A message produced by `commons-python` can be deserialized by `commons-go` (and vice versa).
- Both implementations validate the same set of valid and invalid test fixtures.
- Envelope metadata (timestamps, correlation IDs, schema version) round-trips correctly.
