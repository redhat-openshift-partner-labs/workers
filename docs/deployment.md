# Deployment Guide

---

## Overview

Workers are deployed as container images to Kubernetes.

```mermaid
flowchart LR
    subgraph Git
        F["feature/*\nhotfix/*"] -->|PR + CI| DEV[develop]
        DEV -->|merge commit PR| MAIN[main]
        MAIN -->|git tag\netl/v1.0.0| TAG([release tag])
    end

    subgraph CI / Build
        MAIN -->|push triggers CI| BUILD[Build image\nghcr.io/org/worker:sha]
    end

    subgraph CD — Deployment Repo
        BUILD -->|bot updates image tag| DR_DEV[dev overlay]
        DR_DEV -->|manual promote| DR_STG[staging overlay]
        DR_STG -->|manual promote\n+ approval| DR_PROD[prod overlay]
    end

    subgraph Kubernetes
        DR_DEV -->|ArgoCD sync| K_DEV[dev cluster]
        DR_STG -->|ArgoCD sync| K_STG[staging cluster]
        DR_PROD -->|ArgoCD sync| K_PROD[prod cluster]
    end
```

> **Hotfix shortcut:** `hotfix/*` branches PR directly into `main`, then cherry-pick back to `develop`.
> See [CONTRIBUTING.md](../CONTRIBUTING.md) for the full branching and PR workflow.

---

## Image Tagging

CI tags every image built from `main` with the Git SHA:

```
ghcr.io/org/worker-etl:abc1234
```

For releases, we additionally tag with the worker-scoped version:

```
ghcr.io/org/worker-etl:v1.2.0
```

Release tags in Git follow the pattern `{worker}/v{semver}`:

```bash
git tag etl/v1.2.0
git push origin etl/v1.2.0
```

---

## k8s/ Directory Structure

Each worker's `k8s/` directory contains Kustomize base manifests:

```
etl/k8s/
├── kustomization.yaml
├── deployment.yaml
├── service.yaml          # if the worker exposes an HTTP health endpoint
├── configmap-etl-schema.yaml
└── hpa.yaml              # horizontal pod autoscaler (if applicable)
```

**What goes in `configmap-etl-schema.yaml`:** Some workers (like ETL) mount JSON Schema files as ConfigMaps for runtime validation. This ConfigMap is generated from `schemas/` and baked into the k8s manifests at build time. This allows schema updates to propagate without rebuilding the worker image.

### Environment-specific overlays

Environment overlays (dev, staging, prod) live in a **separate deployment repository** (e.g., `org/k8s-deployments`) that references the base manifests and overrides image tags, replica counts, resource limits, and environment variables per cluster.

```
k8s-deployments/
├── workers/
│   ├── dev/
│   │   ├── kustomization.yaml     # patches image tag to :latest-dev
│   │   └── etl-patch.yaml
│   ├── staging/
│   │   └── ...
│   └── prod/
│       └── ...
```

> **Decision:** Keeping overlays in a separate repo ensures the workers monorepo
> stays focused on source code and base manifests, while the deployment repo
> tracks what's running where.

---

## CD Pipeline (ArgoCD)

ArgoCD watches the deployment repository and syncs manifests to the target cluster. The flow:

1. CI pushes a new image to GHCR.
2. CI (or a bot) opens a PR in the deployment repo updating the image tag for the affected worker.
3. PR is reviewed and merged.
4. ArgoCD detects the change and syncs.

### Promotion between environments

```
dev  →  staging  →  prod
```

- **dev:** Auto-synced from the deployment repo's `dev/` overlays. Image tags update automatically on every `main` merge.
- **staging:** Manual promotion. Update the staging overlay's image tag to a specific SHA or release tag, merge the PR.
- **prod:** Manual promotion with approval. Same process as staging, but the PR requires sign-off from on-call or team lead.

---

## Rollback

To roll back a worker:

1. In the deployment repo, revert the image tag to the previous known-good SHA or release tag.
2. Merge the revert PR.
3. ArgoCD syncs the rollback automatically.

Alternatively, use ArgoCD's UI to manually sync to a previous Git revision of the deployment repo.

---

## Health Checks

Workers that consume from RabbitMQ should expose a minimal HTTP health endpoint (e.g., `/healthz` on port 8080) that reports:

- **Liveness:** Process is running and not deadlocked.
- **Readiness:** RabbitMQ connection is established and the worker is consuming.

Kubernetes probes are configured in `deployment.yaml`. Workers without an HTTP endpoint should use `exec` probes or rely on Kubernetes restart policies with appropriate `livenessProbe` commands.

---

## Secrets

Secrets (RabbitMQ credentials, API keys, etc.) are managed via:

- **Kubernetes Secrets** injected as environment variables in the deployment manifest.
- **External Secrets Operator** (if used) to sync from a vault (e.g., AWS Secrets Manager, HashiCorp Vault).

> Secrets are never stored in the workers monorepo or the deployment repo.
