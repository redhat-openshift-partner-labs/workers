# Testing Deployments

This directory contains test infrastructure and scripts for PoC testing.

## Files

### Deployment Files

#### rabbitmq-deployment.yaml

Simple RabbitMQ deployment with management UI.

- **Namespace**: `rabbitmq`
- **Credentials**: admin/admin123
- **Ports**: 5672 (AMQP), 15672 (Management UI)
- **Storage**: ephemeral (emptyDir)

**Not for production!** Use RabbitMQ Operator or managed service for production.

#### mailhog-deployment.yaml

Mailhog fake SMTP server for capturing test emails.

- **Namespace**: `partner-labs`
- **Ports**: 1025 (SMTP), 8025 (Web UI)
- **Purpose**: Captures all emails without actually sending them

Perfect for testing email templates and formatting.

### Test Scripts

#### deploy-test.sh

Automated deployment script that deploys all test infrastructure:
- RabbitMQ (in `rabbitmq` namespace)
- Mailhog (in `partner-labs` namespace)
- Email Service (in `partner-labs` namespace)

Waits for all pods to be ready and displays access URLs.

#### cleanup-test.sh

Removes all test deployments:
- Email Service
- Mailhog
- RabbitMQ and its namespace

Prompts for confirmation before deleting.

#### test-publish.sh

Publishes a test message to RabbitMQ using `amqp-tools`.

**Usage**:
```bash
./test-publish.sh your-email@example.com
```

**Requires**: `amqp-tools` package (`brew install amqp-tools` on macOS)

## Quick Start

Deploy everything:
```bash
# From the testing directory
./deploy-test.sh

# Or from project root
./testing/deploy-test.sh
```

Cleanup:
```bash
# From the testing directory
./cleanup-test.sh

# Or from project root
./testing/cleanup-test.sh
```

## Manual Deployment

### Deploy RabbitMQ

```bash
oc create namespace rabbitmq
oc apply -f testing/rabbitmq-deployment.yaml
oc wait --for=condition=ready pod -l app=rabbitmq -n rabbitmq --timeout=120s
```

### Deploy Mailhog

```bash
oc apply -f testing/mailhog-deployment.yaml
oc wait --for=condition=ready pod -l app=mailhog -n opl-email-service --timeout=60s
```

## Access

### RabbitMQ Management UI

**Via Route** (if exposed):
```bash
oc get route rabbitmq-management -n rabbitmq
# Open the URL, login with admin/admin123
```

**Via Port Forward**:
```bash
oc port-forward -n rabbitmq svc/rabbitmq-management 15672:15672
# Open http://localhost:15672 (admin/admin123)
```

### Mailhog Web UI

**Via Route** (if exposed):
```bash
oc get route mailhog-web -n opl-email-service
# Open the URL to see captured emails
```

**Via Port Forward**:
```bash
oc port-forward -n opl-email-service svc/mailhog-web 8025:8025
# Open http://localhost:8025
```

## Production Considerations

These deployments are for **testing only**. For production:

### RabbitMQ

Use one of:
- **RabbitMQ Cluster Operator** (recommended)
- **Managed RabbitMQ** (AWS MQ, CloudAMQP, etc.)
- **StatefulSet deployment** with persistent storage

Requirements:
- Persistent storage
- High availability (multiple replicas)
- Monitoring and alerts
- Regular backups
- Resource limits and requests
- Authentication and TLS

### SMTP

Replace Mailhog with real SMTP service:
- Gmail SMTP (simple, good for testing)
- SendGrid (scalable, good for production)
- AWS SES (AWS-native, cost-effective)
- Mailgun, Postmark, etc.

See `DEPLOYMENT.md` for production SMTP configuration examples.

## Troubleshooting

### RabbitMQ Not Starting

Check logs:
```bash
oc logs -n rabbitmq -l app=rabbitmq
```

Common issues:
- Erlang cookie mismatch
- Port conflicts
- Resource limits

### Mailhog Not Capturing Emails

Verify SMTP service:
```bash
oc get svc mailhog-smtp -n opl-email-service
```

Test connectivity from email service:
```bash
oc exec -n opl-email-service deploy/opl-email-service -- \
  nc -zv mailhog-smtp.opl-email-service.svc.cluster.local 1025
```

## Cleanup

Remove all test resources:
```bash
# Using cleanup script (from testing directory)
./cleanup-test.sh

# Or from project root
./testing/cleanup-test.sh

# Or manually
oc delete -f mailhog-deployment.yaml
oc delete -f rabbitmq-deployment.yaml
oc delete namespace rabbitmq
```
