# Deployment Structure

Kustomize-based deployment with support for multiple namespaces.

## Directory Structure

```
deploy/
├── base/                       # Base resources (no namespace hardcoded)
│   ├── configmap.yaml          # Email service config (patched by overlays)
│   ├── secret.yaml             # SMTP and RabbitMQ credentials
│   ├── deployment.yaml         # Email service deployment
│   ├── serviceaccount.yaml     # Service account
│   ├── rbac.yaml               # Minimal RBAC
│   └── kustomization.yaml      # Base kustomization
├── overlays/                   # Environment-specific configs
│   ├── partner-labs/           # Deploy to partner-labs namespace
│   │   └── kustomization.yaml
│   ├── opl-email-service/      # Deploy to dedicated namespace
│   │   ├── kustomization.yaml
│   │   └── namespace.yaml
│   └── README.md               # Overlay documentation
├── kustomization.yaml          # Top-level (defaults to partner-labs)
└── README.md                   # This file
```

## Quick Start

### Deploy to partner-labs namespace (default)

```bash
# Assumes partner-labs namespace already exists
oc apply -k deploy/overlays/partner-labs

# Or use the default
oc apply -k deploy/
```

### Deploy to dedicated opl-email-service namespace

```bash
# Creates opl-email-service namespace
oc apply -k deploy/overlays/opl-email-service
```

## Why Kustomize Overlays?

The email service needs different configuration depending on which namespace it's deployed to:

1. **Namespace** - Resources must be created in the correct namespace
2. **SMTP hostname** - For testing with Mailhog, the hostname includes the namespace:
   - partner-labs: `mailhog-smtp.partner-labs.svc.cluster.local`
   - opl-email-service: `mailhog-smtp.opl-email-service.svc.cluster.local`

Kustomize overlays solve this by:
- **Base** contains resources without namespace
- **Overlays** set namespace and patch configuration

## How It Works

### Base Resources

All resources in `base/` have **NO namespace field** in metadata:

```yaml
# base/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: opl-email-service  # No namespace!
  labels:
    app: opl-email-service
```

### Overlays Add Namespace

Each overlay's `kustomization.yaml` sets the namespace:

```yaml
# overlays/partner-labs/kustomization.yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: partner-labs  # Injected into all resources

resources:
  - ../../base
```

### Overlays Patch Configuration

Overlays also patch the ConfigMap to match the namespace:

```yaml
# overlays/partner-labs/kustomization.yaml
patches:
  - target:
      kind: ConfigMap
      name: email-service-config
    patch: |-
      - op: replace
        path: /data/smtp_host
        value: "mailhog-smtp.partner-labs.svc.cluster.local"
```

## Verifying Configuration

Preview what will be deployed:

```bash
# See rendered YAML for partner-labs
oc kustomize deploy/overlays/partner-labs

# See what will change (diff against cluster)
oc diff -k deploy/overlays/partner-labs
```

## Customizing for Your Namespace

To deploy to a different namespace:

1. Create new overlay directory:
   ```bash
   mkdir -p deploy/overlays/my-namespace
   ```

2. Create kustomization.yaml:
   ```yaml
   apiVersion: kustomize.config.k8s.io/v1beta1
   kind: Kustomization

   namespace: my-namespace

   resources:
     - ../../base

   patches:
     - target:
         kind: ConfigMap
         name: email-service-config
       patch: |-
         - op: replace
           path: /data/smtp_host
           value: "mailhog-smtp.my-namespace.svc.cluster.local"
   ```

3. Deploy:
   ```bash
   oc apply -k deploy/overlays/my-namespace
   ```

## Production Configuration

For production with real SMTP (not Mailhog), create a production overlay:

```bash
mkdir -p deploy/overlays/production
```

Create `deploy/overlays/production/kustomization.yaml`:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: partner-labs

resources:
  - ../../base

patches:
  # Use Gmail SMTP
  - target:
      kind: ConfigMap
      name: email-service-config
    patch: |-
      - op: replace
        path: /data/smtp_host
        value: "smtp.gmail.com"
      - op: replace
        path: /data/smtp_port
        value: "587"

  # Enable TLS for production SMTP
  - target:
      kind: Deployment
      name: opl-email-service
    patch: |-
      - op: replace
        path: /spec/template/spec/containers/0/env/5/value
        value: "true"
```

Update secrets in base or create overlay-specific secret.

## Common Tasks

### Update SMTP Credentials

Edit `base/secret.yaml` or create overlay-specific secret:

```yaml
# overlays/production/smtp-secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: smtp-credentials
stringData:
  username: "your-email@gmail.com"
  password: "your-app-password"
```

Add to overlay kustomization:

```yaml
resources:
  - ../../base
  - smtp-secret.yaml
```

### Update RabbitMQ Connection

Edit `base/secret.yaml`:

```yaml
stringData:
  url: "amqp://user:pass@rabbitmq.namespace.svc.cluster.local:5672/"
```

### Change Queue Name

Patch in overlay:

```yaml
patches:
  - target:
      kind: ConfigMap
      name: email-service-config
    patch: |-
      - op: replace
        path: /data/queue_name
        value: "my-custom-queue"
```

## Troubleshooting

### Wrong namespace

If resources appear in wrong namespace:

```bash
# Check what will be deployed
oc kustomize deploy/overlays/partner-labs | grep "namespace:"

# Should show: namespace: partner-labs
```

### SMTP connection fails

If using Mailhog and emails aren't received:

1. Verify Mailhog is in same namespace as email service
2. Check configmap has correct SMTP hostname:
   ```bash
   oc get configmap email-service-config -n partner-labs -o yaml | grep smtp_host
   ```
3. Should match: `mailhog-smtp.<namespace>.svc.cluster.local`

### View applied configuration

```bash
# See what's actually deployed
oc get deployment opl-email-service -n partner-labs -o yaml

# Check environment variables
oc set env deployment/opl-email-service -n partner-labs --list
```

## See Also

- `overlays/README.md` - Detailed overlay documentation
- `../DEPLOYMENT.md` - Full deployment guide
- `../testing/README.md` - Testing infrastructure
