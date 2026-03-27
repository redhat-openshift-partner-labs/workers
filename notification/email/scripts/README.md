# Email Message Publishing Script

Python script to publish email messages to RabbitMQ for the OPL Email Service.

## Requirements

```bash
pip install pika
```

## Usage

### Basic cluster-provisioned email

```bash
./publish-email-message.py \
  --rabbitmq-url "amqp://user:pass@rabbitmq.namespace.svc.cluster.local:5672/" \
  --to "partner@example.com" \
  --cluster-id "test-cluster-123" \
  --console-url "https://console.example.com" \
  --credentials-url "https://creds.example.com" \
  --credentials-password "secret123" \
  --timezone "America/New_York" \
  --expiration-date "2026-12-31"
```

### With environment variable

```bash
export RABBITMQ_URL="amqp://user:pass@localhost:5672/"
./publish-email-message.py \
  --to "partner@example.com" \
  --cluster-id "test-123" \
  --console-url "https://console.example.com" \
  --credentials-url "https://creds.example.com" \
  --credentials-password "secret" \
  --timezone "America/New_York" \
  --expiration-date "2026-12-31"
```

### Multiple recipients with CC

```bash
./publish-email-message.py \
  --rabbitmq-url "amqp://localhost:5672/" \
  --to "partner1@example.com" "partner2@example.com" \
  --cc "sponsor@redhat.com" \
  --cluster-id "test-123" \
  --console-url "https://console.example.com" \
  --credentials-url "https://creds.example.com" \
  --credentials-password "secret" \
  --timezone "Europe/London" \
  --expiration-date "2026-12-31"
```

### Cluster expiring warning

```bash
./publish-email-message.py \
  --rabbitmq-url "amqp://localhost:5672/" \
  --to "partner@example.com" \
  --template cluster-expiring \
  --cluster-id "test-123" \
  --expiration-date "2026-03-31" \
  --days-remaining 7
```

## Testing

### Local RabbitMQ Testing

```bash
# Start RabbitMQ with Docker
docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:3-management

# Publish test message
./publish-email-message.py \
  --rabbitmq-url "amqp://guest:guest@localhost:5672/" \
  --to "your-email@example.com" \
  --cluster-id "test-123" \
  --console-url "https://console.example.com" \
  --credentials-url "https://creds.example.com" \
  --credentials-password "secret" \
  --timezone "America/New_York" \
  --expiration-date "2026-12-31" \
  --verbose

# Check RabbitMQ Management UI
# http://localhost:15672 (guest/guest)
```

### In-Cluster Testing

```bash
# Port forward to RabbitMQ
oc port-forward -n rabbitmq-namespace svc/rabbitmq 5672:5672

# Publish message (uses localhost via port-forward)
./publish-email-message.py \
  --rabbitmq-url "amqp://user:pass@localhost:5672/" \
  --to "partner@example.com" \
  --cluster-id "test-cluster" \
  --console-url "https://console.example.com" \
  --credentials-url "https://creds.example.com" \
  --credentials-password "secret" \
  --timezone "America/New_York" \
  --expiration-date "2026-12-31"
```

## Example JSON Files

The `examples/` directory contains sample JSON messages:

- `cluster-provisioned-example.json` - Basic provisioned cluster email
- `cluster-provisioned-with-cc.json` - With CC and multiple recipients
- `cluster-expiring-example.json` - Expiration warning email

### Using Example Files

```bash
# Publish using amqp-publish directly
cat examples/cluster-provisioned-example.json | \
  amqp-publish -u "amqp://localhost:5672/" -r "opl-emails" -p

# Or via RabbitMQ Management UI
# 1. Open http://localhost:15672
# 2. Go to Queues → opl-emails → Publish message
# 3. Paste JSON content
# 4. Click "Publish message"
```

## Integration with Cluster Provisioning

### From Python Provisioning Script

```python
import pika
import json

def send_cluster_provisioned_email(
    cluster_id: str,
    console_url: str,
    credentials_url: str,
    credentials_password: str,
    partner_email: str,
    partner_timezone: str,
    expiration_date: str,
    rabbitmq_url: str = "amqp://rabbitmq.default.svc.cluster.local:5672/"
):
    """Send cluster provisioned email via RabbitMQ."""

    message = {
        "to": [partner_email],
        "subject": f"OpenShift Partner Labs - {cluster_id}",
        "template": "cluster-provisioned",
        "data": {
            "cluster_id": cluster_id,
            "console_url": console_url,
            "credentials_url": credentials_url,
            "credentials_password": credentials_password,
            "timezone": partner_timezone,
            "expiration_date": expiration_date,
        }
    }

    connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
    channel = connection.channel()
    channel.queue_declare(queue="opl-emails", durable=True)

    channel.basic_publish(
        exchange="",
        routing_key="opl-emails",
        body=json.dumps(message),
        properties=pika.BasicProperties(delivery_mode=2)
    )

    connection.close()
    print(f"Email notification queued for {partner_email}")

# Usage in provisioning script
send_cluster_provisioned_email(
    cluster_id="acme-cluster-01",
    console_url="https://console-openshift-console.apps.acme-cluster-01.example.com",
    credentials_url="https://bin.apps.admin.openshiftpartnerlabs.com/?abc123",
    credentials_password="secret123",
    partner_email="partner@acmecorp.com",
    partner_timezone="America/New_York",
    expiration_date="2026-06-30"
)
```

### From Bash/Shell Script

```bash
#!/bin/bash
# cluster-provisioning-complete.sh

CLUSTER_ID="$1"
CONSOLE_URL="$2"
CREDENTIALS_URL="$3"
CREDENTIALS_PASSWORD="$4"
PARTNER_EMAIL="$5"
TIMEZONE="$6"
EXPIRATION_DATE="$7"

# Send email notification
python3 /path/to/publish-email-message.py \
  --rabbitmq-url "${RABBITMQ_URL}" \
  --to "${PARTNER_EMAIL}" \
  --cluster-id "${CLUSTER_ID}" \
  --console-url "${CONSOLE_URL}" \
  --credentials-url "${CREDENTIALS_URL}" \
  --credentials-password "${CREDENTIALS_PASSWORD}" \
  --timezone "${TIMEZONE}" \
  --expiration-date "${EXPIRATION_DATE}"
```

## Troubleshooting

### Connection Refused

```
Error: Failed to connect to RabbitMQ: ...
```

**Check**:
1. RabbitMQ is running: `oc get pods -n rabbitmq-namespace`
2. Port forward is active (if testing locally)
3. URL is correct (check host, port, credentials)

### Invalid Message Format

```
Error: invalid email request: ...
```

**Check**:
1. All required fields are present
2. Email addresses are valid format
3. JSON is valid (use `jq` to validate)
4. Template name is correct

### Message Published but No Email Received

**Check**:
1. Email service is running: `oc get pods -n opl-email-service`
2. Email service logs: `oc logs -n opl-email-service -l app=opl-email-service`
3. SMTP configuration is correct
4. Check spam/junk folder
5. For testing, use Mailhog to capture emails

## Help

For detailed message format documentation, see `../MESSAGE_FORMAT.md`

For email service setup and deployment, see `../CLAUDE.md`
