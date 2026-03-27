# Notification Workers

Notification workers send messages through various channels (email, Slack, SMS, etc.) for OpenShift Partner Labs.

## Current Workers

### Email Worker (`email/`)

Sends email notifications via SMTP based on RabbitMQ messages.

- **Queue**: `lab.notify.email`
- **Language**: Python 3.12
- **Features**: Text-only emails, template rendering, retry logic
- **See**: [`email/README.md`](email/README.md) for detailed documentation

**Quick start**:
```bash
cd email
pip install -e '.[dev]'
pytest tests/ -v
python -m notification  # Requires RabbitMQ + SMTP configured
```

## Message Format

All notification workers consume JSON messages from RabbitMQ:

```json
{
  "to": ["partner@example.com"],
  "subject": "OpenShift Partner Labs - cluster-abc-123",
  "template": "cluster-provisioned",
  "data": {
    "cluster_id": "cluster-abc-123",
    "console_url": "https://console.example.com",
    "credentials_url": "https://bin.apps.admin.openshiftpartnerlabs.com/?xyz",
    "credentials_password": "secret123",
    "timezone": "America/New_York",
    "expiration_date": "2026-03-10"
  }
}
```

See [`MESSAGE_FORMAT.md`](MESSAGE_FORMAT.md) for complete specification.

## Adding New Notification Channels

To add a new notification channel (Slack, SMS, webhooks, etc.):

1. **Create subdirectory**: `notification/{channel}/`
2. **Follow the email worker pattern**:
   - RabbitMQ consumer (`worker.py`)
   - Channel-specific client (`{channel}.py`)
   - Configuration (`config.py` with `NOTIFICATION_{CHANNEL}_*` env vars)
   - Templates (if applicable)
   - Tests (`tests/`)
   - Deployment manifests (`deploy/`)
3. **Build container**: `podman build -f notification/{channel}/Containerfile -t worker-notification-{channel} ./notification/{channel}`

Example structure:
```
notification/
├── email/          # Email worker (implemented)
├── slack/          # Slack worker (future)
├── sms/            # SMS worker (future)
└── webhook/        # Generic webhook worker (future)
```

## Architecture

Each notification worker is independent:
- **Stateless**: No shared state between messages
- **Scalable**: Horizontal scaling via replicas
- **Isolated**: Separate queues and configuration per channel
- **Graceful shutdown**: Handles SIGTERM/SIGINT for Kubernetes

## Migration History

This worker was rewritten from Go to Python in March 2026. See [`PYTHON-MIGRATION.md`](PYTHON-MIGRATION.md) for details.

## Documentation

- **Email Worker**: [`email/README.md`](email/README.md)
- **Message Format**: [`MESSAGE_FORMAT.md`](MESSAGE_FORMAT.md)
- **Migration History**: [`PYTHON-MIGRATION.md`](PYTHON-MIGRATION.md)

---

**Maintained By**: OPL Engineering Team
**Last Updated**: 2026-03-25
