# Schema Reference

The ETL worker uses a YAML-based schema to define how raw Google Sheet fields map to the canonical database schema. This document specifies the schema format and all available options.

## Schema Location

- **Kubernetes**: `/etc/etl-schema/schema.yaml` (mounted from ConfigMap `etl-field-schema`)
- **Local development**: `configmap-etl-schema.yaml` (contains the ConfigMap wrapper)

## Schema Structure

```yaml
version: "1.0.0"

generated_fields:
  - db_column: cluster_id
    generator: uuid4

fields:
  - source_key: company_name
    db_column: company_name
    type: string
    required: true

auto_provision_policy:
  complexity_keywords:
    - "gpu"
    - "custom"
```

## Top-Level Keys

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `version` | string | Yes | Schema version (semantic versioning) |
| `fields` | array | Yes | Field mapping definitions |
| `generated_fields` | array | No | System-generated field definitions |
| `auto_provision_policy` | object | No | Auto-provision evaluation rules |

---

## Field Definitions

Each entry in `fields` defines how a source field maps to the database.

### Field Attributes

| Attribute | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `source_key` | string | Yes | - | Field name as it arrives from AppScript (Google Sheet header) |
| `db_column` | string\|null | Yes | - | Target column in the database. `null` = field goes to `extras` JSONB |
| `type` | string | No | `"string"` | Expected type after coercion |
| `required` | boolean | No | `false` | Whether the field must be present and non-empty |
| `default` | string\|null | No | `null` | Default value if field is absent or empty |
| `transform` | string\|null | No | `null` | Transformation to apply after coercion |
| `is_standard_criteria` | boolean | No | `false` | Whether this field is evaluated for auto-provision policy |
| `standard_values` | array | No | `[]` | Allowed values for auto-provision eligibility |

### Supported Types

| Type | Description | Coercion Behavior |
|------|-------------|-------------------|
| `string` | Plain text | Strips whitespace, converts to string |
| `int` | Integer number | Parses as integer, raises `TYPE_COERCION_FAILED` on failure |
| `float` | Decimal number | Parses as float, raises `TYPE_COERCION_FAILED` on failure |
| `bool` | Boolean | `true/1/yes` → `True`, everything else → `False` |
| `datetime` | ISO 8601 timestamp | Parses ISO format, raises `INVALID_DATETIME` on failure |
| `email` | Email address | Validates format with regex, raises `MALFORMED_EMAIL` on failure |

### Supported Transforms

Transforms modify the coerced value before storing.

| Transform | Input | Output | Description |
|-----------|-------|--------|-------------|
| `split_name_first` | `"Jane Doe"` | `"Jane"` | Extracts first word as first name |
| `split_name_last` | `"Jane Doe"` | `"Doe"` | Extracts everything after first word as last name |

**Note**: One `source_key` can map to multiple `db_column` values using different transforms. For example, `primary_contact_name` maps to both `primary_first` and `primary_last`.

### Field Examples

**Required field with validation**:
```yaml
- source_key: primary_contact_email
  db_column: primary_email
  type: email
  required: true
```

**Optional field with default**:
```yaml
- source_key: secondary_contact_name
  db_column: secondary_first
  type: string
  required: false
  default: ""
  transform: split_name_first
```

**Field going to extras JSONB**:
```yaml
- source_key: statement_of_work
  db_column: null  # Goes to extras
  type: string
  required: false
  default: ""
```

**Standard criteria field**:
```yaml
- source_key: cluster_size
  db_column: cluster_size
  type: string
  required: false
  default: ""
  is_standard_criteria: true
  standard_values:
    - ""
    - "Small"
    - "Standard"
```

---

## Generated Fields

Fields the ETL worker creates (not from the Google Sheet).

### Generated Field Attributes

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `db_column` | string | Yes | Target column in the database |
| `generator` | string | Yes | Generator function to use |
| `value` | string | No | Static value (only when `generator: static`) |

### Supported Generators

| Generator | Output | Description |
|-----------|--------|-------------|
| `uuid4` | `"550e8400-e29b-41d4-a716-446655440000"` | Random UUID v4 |
| `short_id` | `"opl-a7f3b2"` | Short, DNS-safe identifier |
| `derive_cluster_name` | `"acme-fsi-demo"` | DNS-safe name from company + project |
| `static` | (value from `value` attribute) | Fixed value for all records |

### Generated Field Examples

```yaml
generated_fields:
  - db_column: cluster_id
    generator: uuid4

  - db_column: generated_name
    generator: short_id

  - db_column: cluster_name
    generator: derive_cluster_name

  - db_column: cloud_provider
    generator: static
    value: "aws"

  - db_column: state
    generator: static
    value: "Pending"
```

---

## Auto-Provision Policy

Defines rules for determining if a request qualifies for automatic provisioning.

### Policy Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `complexity_keywords` | array | Keywords in `description` that trigger non-standard status |

### Evaluation Logic

A request is **standard** (auto-provisionable) if ALL of the following are true:

1. Every field with `is_standard_criteria: true` has a value in its `standard_values` list
2. The `description` field does not contain any `complexity_keywords` (case-insensitive)
3. The `note` field is empty or contains 10 or fewer characters

### Policy Example

```yaml
auto_provision_policy:
  complexity_keywords:
    - "gpu"
    - "GPU"
    - "bare metal"
    - "baremetal"
    - "custom"
    - "assistance"
    - "help"
    - "troubleshooting"
```

---

## Extras JSONB Catchall

Fields are routed to the `extras` JSONB column when:

1. `db_column: null` is explicitly set
2. The field is not in the schema at all (unknown fields are captured automatically)

**Exception**: These metadata fields are intentionally dropped and do not appear in `extras`:
- `timestamp` (form submission time)
- `status` (sheet status)
- `evaluated_on` (sheet metadata)
- `email` (submitter email, used for audit only)

---

## Schema Loading

The schema is loaded at worker startup via `load_schema()`:

```python
from schema import load_schema

schema = load_schema("/etc/etl-schema/schema.yaml")
print(f"Schema v{schema.version} loaded")
print(f"  {len(schema.fields)} field mappings")
print(f"  {len(schema.generated_fields)} generated fields")
```

### Pre-Built Lookups

After loading, the schema provides efficient lookup methods:

| Property/Method | Description |
|-----------------|-------------|
| `schema.required_source_keys` | Set of source keys that are required |
| `schema.fields_for(source_key)` | List of `FieldDef` objects for a source key |
| `schema.standard_criteria_fields` | List of fields used in auto-provision evaluation |
| `schema.all_known_source_keys` | Set of all source keys defined in the schema |
| `schema.complexity_keywords` | List of keywords that trigger non-standard status |

---

## Adding New Fields

To add a new field mapping:

1. Edit `configmap-etl-schema.yaml`
2. Add the field definition under `fields:`
3. Restart the worker (or update the ConfigMap in Kubernetes)

**Example**: Adding a new required field
```yaml
- source_key: budget_code
  db_column: budget_code
  type: string
  required: true
```

**Example**: Adding a new optional field to extras
```yaml
- source_key: custom_notes
  db_column: null
  type: string
  required: false
  default: ""
```

## Related Documentation

- [Developer Guide](./developer-guide.md) - Adding new transforms and generators
- [Troubleshooting](./troubleshooting.md) - Common schema-related errors
- [Parent: Schema Evolution](../../docs/schema-evolution.md) - Breaking change policy
