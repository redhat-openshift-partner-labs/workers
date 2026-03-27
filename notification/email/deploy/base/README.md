# Base Kustomize Resources

This directory contains the base Kubernetes resources for the OPL Email Service.

## Setup

Before deploying, you must configure secrets:

```bash
# Copy the example secret file
cp secret.yaml.example secret.yaml

# Edit with your credentials
vi secret.yaml
```

**Important**: `secret.yaml` is in `.gitignore` and should never be committed to git.

## Files

- `secret.yaml.example` - Template with placeholder credentials (committed to git)
- `secret.yaml` - Your actual credentials (NOT committed to git)
- `configmap.yaml` - Non-sensitive configuration
- `deployment.yaml` - Email service deployment
- `serviceaccount.yaml` - Service account
- `rbac.yaml` - Minimal RBAC
- `kustomization.yaml` - Base kustomization

## Configuration

See `../../CONFIGURATION.md` for detailed configuration instructions.

## Usage

Don't deploy from base directly - use overlays:

```bash
# Deploy to partner-labs namespace
oc apply -k ../overlays/partner-labs

# Deploy to opl-email-service namespace
oc apply -k ../overlays/opl-email-service
```
