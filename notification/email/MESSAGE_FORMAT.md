# RabbitMQ Message Format for OPL Email Service

## Overview

The OPL Email Service consumes JSON messages from RabbitMQ and sends emails to partners. This document defines the exact message format required.

## Queue Details

- **Queue Name**: `opl-emails`
- **Exchange**: (default/direct)
- **Routing Key**: `opl-emails`
- **Message Format**: JSON
- **Durability**: Queue should be durable
- **Auto-delete**: No

## Message Structure

### Required Fields

```json
{
  "to": ["partner@example.com"],
  "subject": "OpenShift Partner Labs - cluster-abc-123",
  "template": "lab_ready",
  "data": {
    "cluster_id": "cluster-abc-123",
    "console_url": "https://console-openshift-console.apps.cluster-abc-123.example.com",
    "credentials_url": "https://bin.apps.admin.openshiftpartnerlabs.com/?abc123",
    "credentials_password": "secret-password-123",
    "timezone": "America/New_York",
    "expiration_date": "2026-04-15"
  }
}
```

### Optional Fields

```json
{
  "to": ["partner@example.com"],
  "cc": ["sponsor@redhat.com"],
  "bcc": ["admin@openshiftpartnerlabs.com"],
  "subject": "...",
  "template": "...",
  "data": { ... }
}
```

## Field Definitions

### Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `to` | array of strings | Yes | Primary recipient email addresses |
| `cc` | array of strings | No | CC recipient email addresses |
| `bcc` | array of strings | No | BCC recipient email addresses |
| `subject` | string | Yes | Email subject line |
| `template` | string | Yes | Template name (`lab_ready`, `lab_expiring`, or `lab_deprovisioned`) |
| `data` | object | Yes | Template-specific data (see below) |

### Data Fields (for `lab_ready` template)

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `cluster_id` | string | Yes | Unique cluster identifier | `"partner-cluster-123"` |
| `console_url` | string | Yes | OpenShift console URL | `"https://console-openshift-console.apps.cluster.example.com"` |
| `credentials_url` | string | Yes | Password-protected URL with credentials | `"https://bin.apps.admin.openshiftpartnerlabs.com/?xyz#hash"` |
| `credentials_password` | string | Yes | Password to access credentials URL | `"ooju5taigee123"` |
| `timezone` | string | Yes | Partner's timezone | `"America/New_York"`, `"Europe/London"`, `"Asia/Tokyo"` |
| `expiration_date` | string | Yes | Cluster expiration date (YYYY-MM-DD) | `"2026-04-15"` |

### Data Fields (for `lab_expiring` template)

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `cluster_id` | string | Yes | Unique cluster identifier | `"partner-cluster-123"` |
| `expiration_date` | string | Yes | When cluster will expire | `"2026-04-15"` |
| `days_remaining` | number | Yes | Days until expiration | `7` |
| `console_url` | string | No | OpenShift console URL | `"https://console..."` |

### Data Fields (for `lab_deprovisioned` template)

| Field | Type | Required | Description | Example |
|-------|------|----------|-------------|---------|
| `cluster_id` | string | Yes | Unique cluster identifier | `"partner-cluster-123"` |
| `deprovision_date` | string | Yes | Date cluster was deprovisioned | `"2026-04-15"` |
| `deprovision_reason` | string | Yes | Reason for deprovisioning | `"Lab access expired"` |

## Complete Examples

### Example 1: Single Partner, US East Coast

```json
{
  "to": ["john.doe@acmecorp.com"],
  "subject": "OpenShift Partner Labs - acme-test-cluster",
  "template": "lab_ready",
  "data": {
    "cluster_id": "acme-test-cluster",
    "console_url": "https://console-openshift-console.apps.acme-test-cluster.openshiftpartnerlabs.com",
    "credentials_url": "https://bin.apps.admin.openshiftpartnerlabs.com/?68f2a19b#BG18SxrstTBNyv5cE3bwnaSERCMh8yPGKkh3TEy1Papg",
    "credentials_password": "ooju5taigee7Xahdee9u",
    "timezone": "America/New_York",
    "expiration_date": "2026-05-15"
  }
}
```

### Example 2: Multiple Recipients with CC

```json
{
  "to": ["jane.smith@partnercorp.com", "bob.jones@partnercorp.com"],
  "cc": ["sponsor@redhat.com"],
  "subject": "OpenShift Partner Labs - partnercorp-dev-01",
  "template": "lab_ready",
  "data": {
    "cluster_id": "partnercorp-dev-01",
    "console_url": "https://console-openshift-console.apps.partnercorp-dev-01.openshiftpartnerlabs.com",
    "credentials_url": "https://bin.apps.admin.openshiftpartnerlabs.com/?abc123#xyz789",
    "credentials_password": "secret123",
    "timezone": "Europe/London",
    "expiration_date": "2026-06-30"
  }
}
```

### Example 3: Expiration Warning

```json
{
  "to": ["partner@example.com"],
  "subject": "OpenShift Partner Labs - Cluster Expiring Soon",
  "template": "lab_expiring",
  "data": {
    "cluster_id": "test-cluster-123",
    "expiration_date": "2026-03-25",
    "days_remaining": 7,
    "console_url": "https://console-openshift-console.apps.test-cluster-123.openshiftpartnerlabs.com"
  }
}
```

## Timezone Reference

Common timezone values (use IANA timezone database names):

**North America**:
- `America/New_York` - US Eastern
- `America/Chicago` - US Central
- `America/Denver` - US Mountain
- `America/Los_Angeles` - US Pacific
- `America/Toronto` - Canada Eastern

**Europe**:
- `Europe/London` - UK
- `Europe/Paris` - Central European
- `Europe/Berlin` - Germany

**Asia/Pacific**:
- `Asia/Tokyo` - Japan
- `Asia/Singapore` - Singapore
- `Australia/Sydney` - Australia Eastern

## Integration Points

### From Cluster Provisioning Workflow

After Hive successfully provisions a cluster:

1. **Extract cluster metadata**:
   - Cluster ID from ClusterDeployment name
   - Console URL from ClusterDeployment status
   - Admin credentials from `<cluster>-admin-kubeconfig` secret

2. **Create password-protected credentials URL**:
   - Upload credentials to burn-after-read service
   - Get URL and password

3. **Publish message to RabbitMQ**:
   - Use provided Python script
   - Message will be automatically consumed and email sent

### Message Publishing Script

A Python script is provided (`scripts/publish-email-message.py`):
- Requires: `pika` library (`pip install pika`)
- Best for: Integration with Python-based provisioning tools
- Supports: Connection to in-cluster or remote RabbitMQ
- Command-line interface for manual testing

## Validation

The email service validates all incoming messages:

**Validation Checks**:
- ✅ Valid JSON format
- ✅ All required fields present
- ✅ Valid email addresses (RFC 5322 format)
- ✅ Template exists
- ✅ Non-empty subject

**Invalid Messages**:
- Rejected (Nack) and NOT requeued
- Error logged for troubleshooting

**SMTP Failures**:
- Rejected (Nack) and requeued
- Retry logic: 3 attempts with exponential backoff

## Testing

### Local Testing with Docker

```bash
# Start RabbitMQ
docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management

# Publish test message
python scripts/publish-email-message.py \
  --rabbitmq-url "amqp://guest:guest@localhost:5672/" \
  --to "your-email@example.com" \
  --cluster-id "test-123" \
  --console-url "https://console.example.com" \
  --credentials-url "https://creds.example.com" \
  --credentials-password "secret" \
  --timezone "America/New_York" \
  --expiration-date "2026-12-31"
```

### In-Cluster Testing

```bash
# Port forward to RabbitMQ
oc port-forward -n rabbitmq svc/rabbitmq 5672:5672

# Publish message (using localhost via port-forward)
python scripts/publish-email-message.py \
  --rabbitmq-url "amqp://user:pass@localhost:5672/" \
  --to "partner@example.com" \
  --cluster-id "test-cluster" \
  --console-url "https://console.example.com" \
  --credentials-url "https://creds.example.com" \
  --credentials-password "secret" \
  --timezone "America/New_York" \
  --expiration-date "2026-12-31"
```

### Using RabbitMQ Management UI

1. Access management UI: `http://localhost:15672` (guest/guest)
2. Navigate to **Queues** → **opl-emails** → **Publish message**
3. Paste JSON message in **Payload** field
4. Click **Publish message**
5. Check email service logs

## Troubleshooting

### Message Not Being Consumed

**Check**:
1. RabbitMQ connection: `oc logs -n opl-email-service -l app=opl-email-service`
2. Queue exists: Check RabbitMQ management UI
3. Message format: Validate JSON against examples above
4. Consumer running: `oc get pods -n opl-email-service`

### Email Not Received

**Check**:
1. Email service logs for SMTP errors
2. SMTP credentials are correct
3. Recipient address is valid
4. Check spam/junk folder
5. For testing, use Mailhog to capture emails

### Invalid Message Errors

**Common Issues**:
- Missing required fields: Check field names match exactly
- Invalid email address: Use proper format (`user@domain.com`)
- Template not found: Use `lab_ready` or `lab_expiring`
- Invalid JSON: Use JSON validator (e.g., `jq`)

**Example JSON Validation**:
```bash
# Validate JSON syntax
cat message.json | jq .

# Validate and pretty-print
cat message.json | jq -r
```

## Production Recommendations

### Security

1. **RabbitMQ Authentication**:
   - Use dedicated user (not guest)
   - Strong password
   - TLS/SSL encryption

2. **SMTP Credentials**:
   - Store in Kubernetes Secrets
   - Use app-specific passwords (Gmail)
   - Consider dedicated email service (SendGrid, Mailgun)

3. **Credentials URL**:
   - Must use burn-after-read or time-limited access
   - Strong random password generation
   - HTTPS only

### Monitoring

1. **RabbitMQ Metrics**:
   - Queue depth
   - Consumer count
   - Message rate

2. **Email Service Metrics**:
   - Messages processed
   - Send failures
   - SMTP errors

3. **Alerts**:
   - Queue backlog > 10 messages
   - Consumer disconnected
   - High send failure rate

## Support

For issues with:
- **Message format**: Check this document and examples
- **Publishing scripts**: See `scripts/` directory
- **Email service**: Check `opl-email-service/CLAUDE.md`
- **RabbitMQ**: Check cluster admin documentation
