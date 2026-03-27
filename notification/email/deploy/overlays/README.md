# Kustomize Overlays

This directory contains environment-specific configurations for deploying the email service.

## Structure

```
overlays/
├── partner-labs/          # Deploy to existing partner-labs namespace
│   └── kustomization.yaml
├── opl-email-service/     # Deploy to dedicated opl-email-service namespace
│   ├── kustomization.yaml
│   └── namespace.yaml
└── README.md
```

## Usage

### Deploy to partner-labs namespace (recommended)

```bash
# From the opl-email-service directory
oc apply -k deploy/overlays/partner-labs

# Or using the shorthand
oc apply -k deploy/  # defaults to partner-labs overlay
```

### Deploy to opl-email-service namespace

Creates a dedicated `opl-email-service` namespace:

```bash
oc apply -k deploy/overlays/opl-email-service
```

## What the Overlays Do

Each overlay:
1. **Sets the namespace** - All resources deployed to the correct namespace
2. **Patches ConfigMap** - Updates `smtp_host` to match the namespace (for Mailhog testing)
3. **Includes namespace.yaml** (opl-email-service only) - Creates the namespace if needed

### partner-labs overlay

- **Namespace**: `partner-labs` (must already exist)
- **SMTP Host**: `mailhog-smtp.partner-labs.svc.cluster.local`
- **Use when**: Deploying alongside other partner lab infrastructure

### opl-email-service overlay

- **Namespace**: `opl-email-service` (creates if doesn't exist)
- **SMTP Host**: `mailhog-smtp.opl-email-service.svc.cluster.local`
- **Use when**: Want dedicated namespace for email service

## Creating a New Overlay

To deploy to a different namespace:

```bash
# Create new overlay directory
mkdir -p deploy/overlays/my-namespace

# Create kustomization.yaml
cat > deploy/overlays/my-namespace/kustomization.yaml <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: my-namespace

resources:
  - ../../base

# Patch configmap to use correct namespace for Mailhog SMTP
patches:
  - target:
      kind: ConfigMap
      name: email-service-config
    patch: |-
      - op: replace
        path: /data/smtp_host
        value: "mailhog-smtp.my-namespace.svc.cluster.local"
EOF

# Deploy
oc apply -k deploy/overlays/my-namespace
```

## Customizing for Production

For production deployment with real SMTP (not Mailhog):

1. Create a new overlay or copy an existing one
2. Update the ConfigMap patch to use real SMTP server:

```yaml
patches:
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
```

3. Update the Secret with real SMTP credentials (in the overlay):

```bash
cat > deploy/overlays/production/smtp-credentials.yaml <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: smtp-credentials
stringData:
  username: "your-email@gmail.com"
  password: "your-app-password"
EOF
```

4. Add to overlay's kustomization.yaml:

```yaml
resources:
  - ../../base
  - smtp-credentials.yaml
```

5. Update deployment to enable TLS:

```yaml
patches:
  - target:
      kind: Deployment
      name: opl-email-service
    patch: |-
      - op: replace
        path: /spec/template/spec/containers/0/env/4/value
        value: "true"
```

## Verifying Configuration

To preview what will be deployed without actually applying:

```bash
# See rendered YAML
oc kustomize deploy/overlays/partner-labs

# See diff against cluster
oc diff -k deploy/overlays/partner-labs
```

## Testing Different Namespaces

Deploy Mailhog to the same namespace before deploying email service:

```bash
# Update Mailhog namespace in testing/mailhog-deployment.yaml
# Then deploy
oc apply -f testing/mailhog-deployment.yaml
```

The overlay will automatically configure the email service to connect to Mailhog in the same namespace.
