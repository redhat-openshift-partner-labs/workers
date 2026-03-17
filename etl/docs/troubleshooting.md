# Troubleshooting Guide

This guide covers common errors, debugging techniques, and solutions for the ETL worker.

## Transform Errors

Transform errors are structured with a `code` field for programmatic handling and a `message` field for human readability. Failed messages are routed to the `intake.raw.failed` queue.

### MISSING_REQUIRED_FIELD

**Cause**: A required field is missing or empty in the incoming payload.

**Error Structure**:
```json
{
  "code": "MISSING_REQUIRED_FIELD",
  "message": "Required fields missing or empty: company_name, sponsor",
  "missing_fields": ["company_name", "sponsor"]
}
```

**Solutions**:

1. **Check the source data**: Verify the Google Sheet has values in all required columns
2. **Check field names**: Ensure `source_key` in schema matches the exact header from AppScript
3. **Check for whitespace**: Fields containing only whitespace are treated as empty

**Required Fields** (as of schema v1.0.0):
- `company_name`
- `primary_contact_name`
- `primary_contact_email`
- `sponsor`
- `project_name`
- `request_type`
- `openshift_version`
- `description`
- `start_date`
- `lease`

---

### MALFORMED_EMAIL

**Cause**: An email field failed validation.

**Error Structure**:
```json
{
  "code": "MALFORMED_EMAIL",
  "message": "Invalid email format: 'not-an-email'"
}
```

**Solutions**:

1. **Fix the source data**: Ensure valid email format (user@domain.tld)
2. **Check for typos**: Common issues include missing `@` or `.`
3. **Check for extra characters**: Leading/trailing spaces, hidden unicode

**Email Fields**:
- `email` (submitter)
- `primary_contact_email`
- `secondary_contact_email`
- `sponsor`

---

### TYPE_COERCION_FAILED

**Cause**: A value could not be converted to its expected type.

**Error Structure**:
```json
{
  "code": "TYPE_COERCION_FAILED",
  "message": "Cannot coerce 'abc' to int"
}
```

**Solutions**:

1. **Check schema type**: Verify the `type` in schema matches expected data
2. **Check source data**: Ensure numeric fields don't contain text
3. **Add default**: For optional fields, add a `default` value in schema

---

### INVALID_DATETIME

**Cause**: A datetime field could not be parsed.

**Error Structure**:
```json
{
  "code": "INVALID_DATETIME",
  "message": "Cannot parse datetime: '03/15/2026'"
}
```

**Solutions**:

1. **Use ISO 8601 format**: `2026-03-15T00:00:00.000Z`
2. **Check AppScript**: Ensure datetime fields are formatted correctly before sending
3. **Handle timezone**: Use `Z` suffix or explicit offset like `+00:00`

**Datetime Fields**:
- `timestamp`
- `evaluated_on`
- `start_date`

---

### UNEXPECTED_ERROR

**Cause**: An unhandled exception occurred during processing.

**Error Structure**:
```json
{
  "code": "UNEXPECTED_ERROR",
  "message": "KeyError: 'missing_key'"
}
```

**Solutions**:

1. **Check worker logs**: Full stack trace is logged at ERROR level
2. **Reproduce locally**: Use the raw payload from the failed message
3. **Report issue**: If it's a bug in the transform logic

---

## Connection Issues

### RabbitMQ Connection Refused

**Symptom**:
```
pika.exceptions.AMQPConnectionError: Connection refused
```

**Causes**:
- RabbitMQ not running
- Wrong host/port configuration
- Network/firewall blocking connection

**Solutions**:

1. **Verify RabbitMQ is running**:
   ```bash
   # Check if RabbitMQ is listening
   nc -zv localhost 5672

   # Check container status
   podman ps | grep rabbitmq
   ```

2. **Check environment variables**:
   ```bash
   echo $ETL_RABBITMQ_HOST
   echo $ETL_RABBITMQ_PORT
   ```

3. **Check credentials**:
   ```bash
   # Default is guest/guest, only works on localhost
   ETL_RABBITMQ_USER=myuser ETL_RABBITMQ_PASS=mypass python -m worker
   ```

### Authentication Failed

**Symptom**:
```
pika.exceptions.ProbableAuthenticationError: Connection closed
```

**Solutions**:

1. **Verify credentials**: Check `ETL_RABBITMQ_USER` and `ETL_RABBITMQ_PASS`
2. **Check vhost permissions**: User must have access to the configured vhost
3. **Note**: Default `guest` user only works from localhost

---

## Schema Issues

### Schema File Not Found

**Symptom**:
```
FileNotFoundError: [Errno 2] No such file or directory: '/etc/etl-schema/schema.yaml'
```

**Solutions**:

1. **Local development**: Set `ETL_SCHEMA_PATH` to your local schema file
   ```bash
   ETL_SCHEMA_PATH=./configmap-etl-schema.yaml python -m worker
   ```

2. **Kubernetes**: Verify ConfigMap is mounted correctly
   ```bash
   kubectl describe pod worker-etl-xxx | grep -A5 Mounts
   kubectl exec worker-etl-xxx -- cat /etc/etl-schema/schema.yaml
   ```

### Schema Parse Error

**Symptom**:
```
yaml.scanner.ScannerError: mapping values are not allowed here
```

**Solutions**:

1. **Validate YAML syntax**:
   ```bash
   python -c "import yaml; yaml.safe_load(open('schema.yaml'))"
   ```

2. **Check indentation**: YAML is indentation-sensitive
3. **Check for tabs**: Use spaces only

### ConfigMap Wrapper Issue

**Symptom** (local development):
```
KeyError: 'fields'
```

**Cause**: Loading the full ConfigMap file instead of extracting the inner YAML.

**Solution**: For tests, extract the inner `schema.yaml`:
```python
raw = yaml.safe_load(Path("configmap-etl-schema.yaml").read_text())
inner_yaml = raw["data"]["schema.yaml"]
```

For the worker, point to a plain YAML file (not ConfigMap wrapper).

---

## Message Issues

### Messages Stuck in Queue

**Symptom**: Messages accumulate in `intake.raw` but aren't processed.

**Causes**:
- Worker not running or crashed
- Worker stuck processing a message
- Prefetch exhausted

**Solutions**:

1. **Check worker status**:
   ```bash
   kubectl get pods -l app=worker-etl
   kubectl logs -f deployment/worker-etl
   ```

2. **Check for blocked messages**: Look for errors in logs around the stuck message

3. **Restart worker**: If stuck, restart to reset state

### Messages Going to Failed Queue

**Symptom**: All messages end up in `intake.raw.failed`.

**Solutions**:

1. **Inspect failed messages**: Use RabbitMQ Management UI or:
   ```bash
   # Peek at failed queue (don't ack)
   rabbitmqadmin get queue=intake.raw.failed count=1
   ```

2. **Check error details**: The `error` field contains the structured error
   ```json
   {
     "error": {
       "code": "MISSING_REQUIRED_FIELD",
       "message": "...",
       "raw_row": { ... }
     }
   }
   ```

3. **Fix and replay**: Correct the source data and resubmit, or manually move messages back to `intake.raw`

---

## Container Issues

### Container Won't Start

**Symptom**: Container exits immediately or enters CrashLoopBackOff.

**Solutions**:

1. **Check logs**:
   ```bash
   kubectl logs worker-etl-xxx --previous
   podman logs worker-etl
   ```

2. **Check schema mount**:
   ```bash
   kubectl describe pod worker-etl-xxx | grep -A10 Volumes
   ```

3. **Check environment**:
   ```bash
   kubectl exec worker-etl-xxx -- env | grep ETL_
   ```

### Import Errors

**Symptom**:
```
ModuleNotFoundError: No module named 'pika'
```

**Solution**: Rebuild container with all dependencies:
```bash
podman build --no-cache -f etl/Containerfile -t worker-etl .
```

---

## Debugging Techniques

### Enable Debug Logging

```bash
# Set Python logging to DEBUG
export PYTHONUNBUFFERED=1
python -c "
import logging
logging.basicConfig(level=logging.DEBUG)
from worker import main
main()
"
```

### Test Transform Locally

```python
# test_local.py
import yaml
from pathlib import Path
from schema import load_schema
from transform import transform

# Load schema from ConfigMap file
raw = yaml.safe_load(Path("configmap-etl-schema.yaml").read_text())
inner = raw["data"]["schema.yaml"]
Path("/tmp/schema.yaml").write_text(inner)
schema = load_schema("/tmp/schema.yaml")

# Test with a payload
payload = {
    "company_name": "Test Corp",
    "primary_contact_name": "Jane Doe",
    "primary_contact_email": "jane@test.com",
    "sponsor": "sponsor@redhat.com",
    "project_name": "test-project",
    "request_type": "OpenShift",
    "openshift_version": "4.20",
    "description": "Test deployment",
    "start_date": "2026-03-15T00:00:00Z",
    "lease": "1 month",
}

try:
    result = transform(schema, payload)
    print("Success!")
    print(f"Cluster name: {result['db_columns']['cluster_name']}")
    print(f"Is standard: {result['is_standard_config']}")
except Exception as e:
    print(f"Error: {e}")
```

### Inspect Message Envelopes

```python
from envelope import parse_envelope, build_envelope

# Parse incoming message
incoming = parse_envelope(message_body)
print(f"Event: {incoming['event_type']}")
print(f"Correlation ID: {incoming['correlation_id']}")
print(f"Payload: {incoming['payload']}")

# Build outgoing message
outgoing = build_envelope(
    event_type="intake.normalized",
    payload={"test": "data"},
    source="worker-etl",
    correlation_id=incoming["correlation_id"],
    causation_id=incoming["event_id"],
)
```

### RabbitMQ Management CLI

```bash
# List queues with message counts
rabbitmqadmin list queues name messages

# Get messages from a queue (without ack)
rabbitmqadmin get queue=intake.raw.failed count=5

# Purge a queue (destructive!)
rabbitmqadmin purge queue=intake.raw.failed
```

---

## Getting Help

1. **Check logs first**: Most issues are visible in worker logs
2. **Search existing issues**: Check if others have reported the same problem
3. **Report bugs**: https://github.com/your-org/openshift-partner-labs/issues

When reporting issues, include:
- Error message and code
- Relevant log output
- Schema version
- Sample payload (redacted if sensitive)

---

## Related Documentation

- [Schema Reference](./schema-reference.md) - Schema format and field definitions
- [Developer Guide](./developer-guide.md) - Local development setup
- [Parent: Deployment](../../docs/deployment.md) - Kubernetes deployment details
