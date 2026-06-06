# CLAUDE.md

This file provides context for AI assistants working on the Lifecycle worker.

## Git Policy
- **NEVER push to remote repository** - User handles all pushes manually
- **DO make frequent incremental commits** - Small, focused commits for easy rollback
- **Commit after completing logical units of work** - Don't wait to be asked; commit when a feature, fix, or refactor is complete
- **Ask if uncertain** - If unclear whether work is "complete enough" to commit, ask first
- Use conventional commit messages (feat:, fix:, test:, docs:, refactor:, chore:)

## Role Context
- Expert Python developer
- Expert Microservices developer
- Expert Python test developer

## Development Approach
- TDD: Write tests with pytest first
- Create unit tests for manifest generation, integration tests with RabbitMQ
- Use pytest fixtures for test setup
- Use mermaid for documentation diagrams

## Project Overview

The Lifecycle worker handles cluster lifecycle operations for OpenShift Partner Labs. Its first responsibility is **provisioning**: consuming messages from the `lab.provision.generate-manifests` queue, generating Kustomize overlay manifests, and opening a pull request to the [fleet-clusters](https://github.com/redhat-openshift-partner-labs/fleet-clusters) repo. When that PR merges, Tekton pipelines on the hub cluster provision the actual OpenShift cluster.

**Message Flow:**
```
lab.provision.generate-manifests → [Lifecycle Worker] → PR to fleet-clusters repo
                                                     → lab.provision.manifests-complete (success)
                                                     → lab.provision.generate-manifests.dlq (errors via DLX)
```

**Exchange/Routing:**
- **Exchange**: `opl.provision` (topic)
- **VHost**: `opl`
- **Consume routing key**: `lab.provision.generate-manifests`
- **Publish routing key**: `lab.provision.manifests-complete`

**Tech Stack:**
- **Language**: Python 3.13
- **Message Broker**: RabbitMQ (pika client)
- **Validation**: Pydantic 2.x
- **Config**: pydantic-settings (env-based, 12-factor)
- **GitHub Integration**: TBD (GitHub App, PAT, or PyGithub)
- **Manifest Templating**: Kustomize overlays via YAML generation
- **Testing**: pytest, pytest-cov

**Worker Contract:**
- **Stateless**: No in-memory state between messages
- **Idempotent**: Same message processed twice produces same result (same manifests, same PR or no-op if PR exists)
- **Scalable**: Horizontally via replicas (prefetch=1)
- **Graceful shutdown**: Handles SIGTERM/SIGINT

## Quick Reference

### Commands

```bash
# Install dependencies (from lifecycle/ directory)
pip install -e '.[dev]'

# Run worker locally (requires RabbitMQ at localhost:5672)
python -m worker

# Run tests
pytest -v

# Run tests with coverage
pytest -v --cov=. --cov-report=term-missing

# Build container (from workers/ root directory)
podman build -f lifecycle/Containerfile -t worker-lifecycle .
```

### Key Directories (Planned)

```
lifecycle/
├── config.py                   # pydantic-settings config (LIFECYCLE_* env vars)
├── worker.py                   # LifecycleWorker class, RabbitMQ consume/publish loop
├── manifests.py                # Kustomize overlay generation (patches, kustomization.yaml)
├── github_pr.py                # GitHub PR creation (clone, branch, commit, push, open PR)
├── templates/                  # Jinja2 or YAML templates for patch files (if needed)
├── test_manifests.py           # Unit tests for manifest generation
├── test_worker.py              # Unit tests for message handling
├── pyproject.toml              # Package dependencies
├── Containerfile               # Container build instructions
└── tmp/                        # Example payloads and test scripts (not shipped)
```

## Input Schema: `lab.provision.generate-manifests`

The message payload this worker consumes (from REFERENCE.md v3):

```json
{
  "cluster_name": "string (required)",
  "base_domain": "string (required)",
  "hub_cluster_name": "string (required)",
  "hub_base_domain": "string (required)",
  "gitops_repo": {
    "org": "string",
    "repo": "string",
    "branch": "string (default: main)",
    "base_path": "string"
  },
  "lab_config": {
    "openshift_version": "string",
    "cloud_provider": "aws | azure | gcp | vsphere",
    "region": "string",
    "worker_count": "integer (min 1)",
    "worker_instance_type": "string",
    "network_type": "OVNKubernetes | OpenShiftSDN",
    "ttl_hours": "integer (min 1)"
  },
  "users": [
    {
      "email": "string (required)",
      "name": "string",
      "role": "admin | user (default: user)"
    }
  ],
  "auto_merge": "boolean (default: true)"
}
```

## Output Schema: `lab.provision.manifests-complete`

Published on success:

```json
{
  "cluster_name": "string (required)",
  "pr_url": "string/uri (required)",
  "pr_number": "integer (required)",
  "branch_name": "string (required)",
  "manifests_path": "string (required)",
  "commit_sha": "string",
  "manifests_generated": ["list of file paths"]
}
```

## Fleet-Clusters Manifest Structure

The worker generates a Kustomize overlay under `provision/<cluster-name>/` in the fleet-clusters repo. Each overlay has this structure:

```
provision/<cluster-name>/
├── kustomization.yaml           # References crossplane/ and hive/ subdirs
├── crossplane/
│   ├── kustomization.yaml       # References cluster-templates/<provider>/<variant>/base/crossplane
│   └── patches/
│       ├── user.yaml            # IAM user name patch
│       ├── policy.yaml          # IAM policy name patch
│       ├── policy-attachment.yaml
│       └── access-key.yaml
└── hive/
    ├── kustomization.yaml       # References cluster-templates/<provider>/<variant>/base/hive
    └── patches/
        ├── namespace.yaml       # Cluster namespace
        ├── clusterdeployment.yaml   # Region, image set, secret refs
        ├── install-config.yaml      # install-config content (zones, networking)
        ├── install-config-meta.yaml # Secret metadata name
        ├── machinepool-worker.yaml  # Worker node config
        ├── managedcluster.yaml      # ACM managed cluster + tier label
        └── klusterletaddonconfig.yaml
```

### Template Hierarchy

```
cluster-templates/
  <provider>/          # aws, gcp, azure
    <variant>/base/    # standard (HA), sno (single-node), compact
      crossplane/      # Provider IAM/identity resources
      hive/            # Namespace, ClusterDeployment, MachinePool, etc.
```

### Cross-File Coordination (Critical)

These values **must match** across multiple patch files:
- **Cluster name** → Namespace, ClusterDeployment, MachinePool, ManagedCluster, KlusterletAddonConfig, Secret, all Crossplane resources, install-config `metadata.name`
- **Region** → ClusterDeployment `spec.platform.<provider>.region` and install-config `platform.<provider>.region`
- **Zones** → Must be valid for the chosen region, set in install-config for both `controlPlane` and `compute[0]`
- **Install-config secret name** → `<cluster-name>-install-config` in both ClusterDeployment `installConfigSecretRef` and Secret metadata
- **IAM resource names** → Cross-referenced between Crossplane resources
- **Credential namespace** → Must match the cluster namespace

### One Cluster Per Push

The fleet-clusters EventListener CEL interceptor extracts one cluster name per push. Multiple cluster directories in one push means only the first triggers the pipeline. The worker must create one PR per cluster.

## Architecture Decisions

### Manifest Generation Strategy
Generate patch files (JSON Patch format) that reference base templates in `cluster-templates/`. The worker does NOT copy or inline base templates — it creates only the overlay layer with patches. This mirrors how existing clusters in the repo are structured.

### PR Workflow
1. Clone fleet-clusters (or use shallow clone / GitHub API for tree creation)
2. Create a branch named after the cluster (e.g., `provision/<cluster-name>`)
3. Generate and commit the overlay directory
4. Open a PR targeting `main`
5. PR auto-merges by default after checks pass (controlled by `auto_merge` field in the message)

### GitHub Authentication
TBD — will be either a GitHub App installation token or a Personal Access Token, provided via environment variable or K8s secret.

### Idempotency
If a PR for the same cluster already exists (same branch name), the worker should detect this and either update the existing PR or skip. This prevents duplicate PRs from redelivered messages.

## Code Conventions

### Type Hints
- Use `from __future__ import annotations` for modern syntax
- Full type hints on function signatures
- Use `X | None` instead of `Optional[X]`

### Data Structures
- `@dataclass(frozen=True)` for immutable data containers
- `@dataclass` for mutable containers with `__post_init__` logic
- Pydantic `BaseSettings` for environment configuration

### Naming
- `snake_case` for functions, variables, modules
- `PascalCase` for classes
- Private helpers prefixed with `_`

### Imports
- Group: stdlib, third-party, local
- Use relative imports for local modules (`.config`, `.manifests`, `.github_pr`)

### Error Classes
- Include `code` (machine-readable), `message` (human-readable)
- Provide `to_dict()` method for serialization

## Gotchas

- **Image set ref naming**: The `imageSetRef` in ClusterDeployment uses a naming convention like `img4.21.14-x86-64-appsub`. The worker needs a mapping from OpenShift version strings (e.g., "Latest 4.21") to image set ref names.

- **Region → zone mapping**: The worker needs to know valid availability zones for each region/provider combination. The install-config patches require explicit zone lists.

- **Kustomize validation**: Always validate generated overlays with `kustomize build provision/<cluster-name>` before committing. Invalid YAML or missing patches will fail the PR checks.

- **Provider-specific patches**: AWS, GCP, and Azure have different Crossplane resource types (User/Policy/AccessKey vs ServiceAccount/Key/IAMMember vs Identity/Role/Credential). The manifest generator must handle each provider differently.

- **`cluster-placeholder` convention**: Base templates use `cluster-placeholder` as the default name throughout. Patches replace this with the actual cluster name via JSON Patch `op: replace`.

## Testing

```bash
# Run all tests
pytest -v

# Run specific test class
pytest test_manifests.py::TestManifestGeneration -v

# Run with coverage
pytest --cov=. --cov-report=html
```

### Test Suite (Planned)
- **Framework**: pytest
- **Pattern**: Test classes grouped by feature area:
  - `TestManifestGeneration` — overlay structure, patch content, cross-file consistency
  - `TestProviderVariants` — AWS/GCP/Azure-specific manifest differences
  - `TestPRCreation` — GitHub PR workflow (mocked)
  - `TestMessageHandling` — envelope parsing, schema validation, error routing
  - `TestIdempotency` — duplicate message handling

### Testing Guidelines
- Use example payloads from `tmp/intake-normalized-payload.json` as base
- Test cross-file consistency (cluster name matches in all patches)
- Test all provider/variant combinations
- Mock GitHub API calls in PR tests
- Validate generated YAML with `kustomize build` in integration tests

## Dependencies

From `pyproject.toml` (current + planned):
- `pika>=1.3.2` — RabbitMQ client
- `pydantic>=2.7.0` — Validation and type coercion
- `pyyaml>=6.0` — YAML generation for manifests
- `pydantic-settings>=2.3.0` — Env-based config

Dev dependencies:
- `pytest>=8.0`
- `pytest-cov>=5.0`

GitHub integration dependency TBD (PyGithub, ghapi, or subprocess `gh`).

## Environment Variables

All variables use the `LIFECYCLE_` prefix (configured in `Settings.model_config`):

| Variable | Default | Description |
|----------|---------|-------------|
| `LIFECYCLE_RABBITMQ_HOST` | `localhost` | RabbitMQ hostname |
| `LIFECYCLE_RABBITMQ_PORT` | `5672` | RabbitMQ port |
| `LIFECYCLE_RABBITMQ_USER` | `guest` | RabbitMQ username |
| `LIFECYCLE_RABBITMQ_PASS` | `guest` | RabbitMQ password |
| `LIFECYCLE_RABBITMQ_VHOST` | `opl` | RabbitMQ virtual host |
| `LIFECYCLE_CONSUME_QUEUE` | `lab.provision.generate-manifests` | Queue to consume from |
| `LIFECYCLE_PUBLISH_EXCHANGE` | `opl.provision` | Exchange to publish to |
| `LIFECYCLE_PUBLISH_QUEUE` | `lab.provision.manifests-complete` | Routing key for success messages |
| `LIFECYCLE_SOURCE_ID` | `worker-lifecycle` | Worker identity in message envelopes |
| `LIFECYCLE_PREFETCH_COUNT` | `1` | Messages to prefetch |
| `LIFECYCLE_HEALTH_PORT` | `8080` | HTTP health check server port |
| `LIFECYCLE_GITHUB_TOKEN` | _(none)_ | GitHub token for PR creation (TBD: App vs PAT) |
| `LIFECYCLE_FLEET_REPO` | `redhat-openshift-partner-labs/fleet-clusters` | Target repo for PRs |
| `LIFECYCLE_FLEET_BRANCH` | `main` | Base branch for PRs |
