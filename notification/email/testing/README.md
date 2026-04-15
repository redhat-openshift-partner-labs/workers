# Email Notification Worker - Testing

Test infrastructure for the email notification worker using RabbitMQ Cluster Operator with production-like queue topology.

## Prerequisites

### Required

1. **OpenShift CLI (`oc`)** - Must be installed and logged in
2. **RabbitMQ Cluster Operator** - Install via OperatorHub or:
   ```bash
   kubectl apply -f https://github.com/rabbitmq/cluster-operator/releases/latest/download/cluster-operator.yml
   ```

### Optional

- **RabbitMQ Messaging Topology Operator** - For queue/exchange/binding management (usually bundled with Cluster Operator)
- **amqp-tools** - For manual message publishing (`brew install amqp-tools` on macOS)

## Quick Start

### Configure Namespace

All scripts default to the `partnerlabs` namespace. To change it, edit the default in each script or pass it as an argument.

### Deploy Everything

```bash
# From the notification/email directory
./testing/deploy-test.sh
```

This deploys:
1. RabbitMQ Cluster (single replica for testing)
2. Queue Topology (vhost, exchanges, queues, users, permissions)
3. Mailhog (SMTP server for testing)
4. Email Service (notification worker)

### Test It

```bash
# Port forward RabbitMQ
oc port-forward -n partnerlabs svc/queue 5672:5672

# In another terminal, publish test message
./testing/test-publish.sh

# Check worker logs
oc logs -n partnerlabs -l app=opl-email-service -f

# View email in Mailhog
oc port-forward -n partnerlabs svc/mailhog-web 8025:8025
# Then open http://localhost:8025
```

### Cleanup

```bash
./testing/cleanup-test.sh
```

## Configuration

### Namespace

All scripts default to `partnerlabs`. Override with command line argument:

```bash
./deploy-test.sh my-namespace
./cleanup-test.sh my-namespace
```

Or set via environment variable:
```bash
export NAMESPACE=my-namespace
./test-publish.sh
```

### Namespace-Independent Design

Services use short names (same namespace assumed):
- **SMTP**: `mailhog-smtp` (not full FQDN)
- **RabbitMQ**: `queue` (not full FQDN)
- **Kustomize**: Namespace injected dynamically by scripts

## What Gets Deployed

### RabbitMQ Cluster (`rabbitmq-cluster.yaml`)

- **Cluster Name**: `queue`
- **Replicas**: 1 (testing only, use 3+ for production)
- **Storage**: 5Gi persistent volume
- **Management UI**: Available on port 15672
- **AMQP**: Available on port 5672

### Queue Topology (`queue-topology/`)

Declarative topology matching production:

**Vhost**: `opl`

**Exchanges**:
- `opl.notify` - Notification results
- `opl.handoff` - Inter-worker handoffs
- `opl.provision` - Provisioning events
- `opl.dlx` - Dead letter exchange

**Queues** (all quorum type):
- `notify.user.lab-ready`
- `notify.user.lab-deprovisioned`
- `notify.user.lab-expiring`
- `notify.admin.failure`
- `notify.admin.timeout`
- `lab.provision.pr.approval-required`
- `handoff.welcome-email.send`

**User**: `user-worker-notification`
- Credentials: Auto-generated in secret `user-worker-notification-user-credentials`
- Permissions: Least-privilege (write to notify/handoff exchanges, read from notify queues)

### Mailhog (`mailhog-deployment.yaml`)

- **SMTP**: Port 1025 (captures all emails)
- **Web UI**: Port 8025 (view captured emails)
- **Purpose**: Test email delivery without sending real emails

### Email Service

- **Image**: `quay.io/dcurran/opl-email-service`
- **Configuration**: `deploy/overlays/partner-labs/`
- **Consumes**: All notify queues
- **Publishes**: Results to `opl.notify` exchange

## Access

### RabbitMQ Management UI

Get admin credentials:
```bash
# Username
oc get secret queue-default-user -n partnerlabs -o jsonpath='{.data.username}' | base64 -d

# Password
oc get secret queue-default-user -n partnerlabs -o jsonpath='{.data.password}' | base64 -d
```

Access UI:
```bash
# Via port-forward
oc port-forward -n partnerlabs svc/queue 15672:15672
# Then open http://localhost:15672

# Via route (if created)
oc get route rabbitmq-management -n partnerlabs
```

### Mailhog Web UI

```bash
# Via port-forward
oc port-forward -n partnerlabs svc/mailhog-web 8025:8025
# Then open http://localhost:8025

# Via route (if created)
oc get route mailhog-web -n partnerlabs
```

### Worker Logs

```bash
oc logs -n partnerlabs -l app=opl-email-service -f
```

## Testing

### Publish Test Message

The `test-publish.sh` script automatically:
- Fetches RabbitMQ credentials from cluster
- Publishes to `opl.notify` exchange
- Routes to `notify.user.lab-ready` queue

```bash
# Port forward first
oc port-forward -n partnerlabs svc/queue 5672:5672

# Publish with default recipient
./testing/test-publish.sh

# Publish to specific email
./testing/test-publish.sh user@example.com
```

### Manual Publishing

```bash
# Get credentials
USER=$(oc get secret user-worker-notification-user-credentials -n partnerlabs -o jsonpath='{.data.username}' | base64 -d)
PASS=$(oc get secret user-worker-notification-user-credentials -n partnerlabs -o jsonpath='{.data.password}' | base64 -d)

# Publish using amqp-tools
amqp-publish -u "amqp://${USER}:${PASS}@localhost:5672/opl" \
  -e "opl.notify" \
  -r "notify.user.lab-ready" \
  -b '{
    "to": ["test@example.com"],
    "subject": "Test",
    "template": "lab_ready",
    "data": {
      "cluster_id": "test-001",
      "partner_name": "Test Partner",
      "console_url": "https://console.example.com",
      "api_url": "https://api.example.com:6443",
      "credentials_url": "https://creds.example.com/test",
      "credentials_password": "test123",
      "timezone": "America/New_York",
      "business_hours": "9am-5pm EST",
      "expiration_date": "2026-12-31",
      "expiration_days": 30
    }
  }'
```

### Verify Queue Topology

```bash
# List queues and message counts
oc exec -n partnerlabs queue-server-0 -- rabbitmqctl list_queues -p opl name messages

# List exchanges
oc exec -n partnerlabs queue-server-0 -- rabbitmqctl list_exchanges -p opl name type

# Check user permissions
oc exec -n partnerlabs queue-server-0 -- rabbitmqctl list_permissions -p opl
```

## Troubleshooting

### Worker Not Starting

**Check credentials secret exists**:
```bash
oc get secret user-worker-notification-user-credentials -n partnerlabs
```

If missing, wait 30-60 seconds for RabbitMQ Messaging Topology Operator to create it, then check:
```bash
oc get user.rabbitmq.com user-worker-notification -n partnerlabs -o yaml
```

**Check worker logs**:
```bash
oc logs -n partnerlabs -l app=opl-email-service
```

Common issues:
- Secret not created yet (Topology Operator creates after User CR reconciles)
- Wrong namespace
- RabbitMQ cluster not ready

### Messages Not Being Consumed

**Check queue has messages**:
```bash
oc exec -n partnerlabs queue-server-0 -- rabbitmqctl list_queues -p opl name messages
```

**Verify worker is consuming**:
```bash
oc logs -n partnerlabs -l app=opl-email-service | grep "Subscribing to queue"
```

**Check permissions**:
```bash
oc exec -n partnerlabs queue-server-0 -- rabbitmqctl list_permissions -p opl
```

Worker user should have:
- Configure: `""` (empty - no configure permission)
- Write: `^opl\.(notify|handoff)$`
- Read: `^(notify\.(user|admin)\.[a-z-]+|lab\.provision\.pr\.approval-required|handoff\.welcome-email\.send)$`

### Topology Resources Not Created

**Check operator is running**:
```bash
oc get pods -n rabbitmq-system
```

**Check operator logs**:
```bash
oc logs -n rabbitmq-system -l app.kubernetes.io/name=messaging-topology-operator
```

**Verify CRDs installed**:
```bash
oc get crd | grep rabbitmq.com
```

Should see: `queues`, `exchanges`, `bindings`, `vhosts`, `users`, `permissions`

### Template Not Found

Worker looks for templates in `/app/notification/templates/`. Available templates:
- `lab_ready.txt` - Sent when cluster is ready for use
- `lab_expiring.txt` - Sent when cluster is expiring soon
- `lab_deprovisioned.txt` - Sent when cluster has been deleted

Ensure template name in message doesn't include `.txt` extension.

## Production vs Testing

This testing setup differs from production:

| Aspect | Testing | Production |
|--------|---------|------------|
| Replicas | 1 | 3+ |
| Storage | 5Gi | 50Gi+ |
| TLS | Disabled | Enabled |
| Namespace | `partnerlabs` | `queue` (RabbitMQ) + `partner-labs` (worker) |
| Credentials | Auto-generated | Sealed Secrets |
| Topology | Subset | Full (from `queue` repo) |

## Files Reference

### Scripts

- **deploy-test.sh** - Deploy all test infrastructure
- **cleanup-test.sh** - Remove all test resources
- **test-publish.sh** - Publish test message to queue
- **check-operators.sh** - Verify RabbitMQ operators are installed

### Manifests

- **rabbitmq-cluster.yaml** - RabbitMQ Cluster CR (operator auto-creates ServiceAccount)
- **mailhog-deployment.yaml** - Mailhog deployment + services
- **queue-topology/** - Kustomize directory with notification worker topology

## Related Documentation

- `../deploy/README.md` - Production deployment with Kustomize
- `../README.md` - Email worker overview
- `../../CLAUDE.md` - Workers architecture
