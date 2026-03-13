# Contributing to the Workers Monorepo

---

## Prerequisites

- Python 3.12+
- Podman & Podman Compose
- Git 2.37+ (sparse checkout cone mode support)
- Go 1.22+ (only if working on `commons-go/` or a Go worker)

---

## Local Development Setup

### 1. Clone with sparse checkout

Pick the worker(s) you need. Root-level files are always included.

```bash
git clone --no-checkout git@github.com:org/workers.git
cd workers
git sparse-checkout init --cone
git sparse-checkout set etl commons-python schemas
git checkout main
```

Or use a Makefile shortcut: `make sparse-etl`

### 2. Start infrastructure

A `podman-compose.yaml` at the repo root provides RabbitMQ (and any other shared services) for local development.

```bash
podman compose up -d
```

This starts:
- **RabbitMQ** on `localhost:5672` (management UI at `localhost:15672`, guest/guest)
- Additional services as needed (see `podman-compose.yaml` for the full list)

### 3. Install a worker in dev mode

```bash
cd etl
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]' -e '../commons-python'
```

This installs:
- The worker's own package in editable mode
- `commons` (the shared library) in editable mode from `../commons-python`
- Dev dependencies (pytest, etc.)

### 4. Configure environment

Each worker reads configuration from environment variables via `pydantic-settings`. Copy the example env file and adjust as needed:

```bash
cp .env.example .env
# Edit .env — typical vars: RABBITMQ_HOST, RABBITMQ_PORT, QUEUE_NAME, LOG_LEVEL
```

> **Convention:** Every worker directory should contain a `.env.example` listing all required and optional variables with defaults annotated.

### 5. Run the worker locally

```bash
python -m etl.src
```

Or via Make:

```bash
make run-etl
```

### 6. Run tests

```bash
# Single worker
make test-etl

# Under the hood:
cd etl && pytest tests/ -v
```

---

## Makefile Targets

The root `Makefile` provides convenience targets. Pattern:

| Target | What it does |
|---|---|
| `make sparse-{worker}` | Sparse checkout for that worker + commons + schemas |
| `make sparse-all` | Disable sparse checkout (full repo) |
| `make test-{worker}` | Run pytest for that worker |
| `make test-all` | Run tests for all workers |
| `make build-{worker}` | Podman build from repo root |
| `make build-all` | Podman build for all workers |
| `make run-{worker}` | Run worker locally (requires `.env` + local RabbitMQ) |
| `make lint` | Run linter across all Python code |

---

## Branch Naming

```
feature/{worker-or-scope}-{short-description}
```

Examples:
- `feature/etl-add-gpu-field`
- `feature/commons-add-retry-helper`
- `feature/schemas-add-deprovision-v2`
- `fix/notification-dlq-reconnect`
- `hotfix/etl-null-pointer`

---

## PR Workflow

### Standard flow

```
feature/*  →  PR into develop  →  PR into main
```

1. Create a feature branch from `develop`.
2. Open a PR into `develop`. CI runs automatically for affected workers (path-filtered).
3. Require at least **1 approval** from a worker's CODEOWNERS.
4. Squash-merge into `develop`.
5. `develop → main` promotion is done via a **merge commit PR** (not squash) to preserve history. This is typically done on a regular cadence (e.g., weekly) or on-demand for urgent changes.

### Commons and schema changes

Changes to `commons-python/`, `commons-go/`, or `schemas/` trigger CI for **all** affected workers. These PRs require:
- Approval from the commons/schemas CODEOWNERS
- All worker CI jobs to pass (since the change affects everyone)

### Hotfix flow

For critical fixes to `main` that can't wait for the develop cycle:

```
hotfix/*  →  PR into main  →  cherry-pick back into develop
```

---

## Adding a New Worker

### 1. Scaffold the directory

```bash
mkdir -p new-worker/{src,tests,k8s}
touch new-worker/src/{__init__.py,__main__.py,config.py,worker.py}
touch new-worker/tests/__init__.py
touch new-worker/.env.example
```

### 2. Create `pyproject.toml`

```toml
[project]
name = "worker-new-worker"
version = "0.1.0"
dependencies = [
    "commons",
    "pydantic-settings>=2.3.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]
```

### 3. Create `Containerfile`

Follow the established pattern — build from repo root, copy commons first:

```dockerfile
FROM python:3.12-slim
WORKDIR /app

COPY commons-python/ /app/commons-python/
RUN pip install --no-cache-dir /app/commons-python/

COPY new-worker/ /app/new-worker/
RUN pip install --no-cache-dir /app/new-worker/

RUN useradd -r -s /bin/false newworker
USER newworker
ENTRYPOINT ["python", "-m", "new_worker.src"]
```

### 4. Add CI workflow

Create `.github/workflows/ci-new-worker.yaml` following the pattern in the README. Ensure `paths:` includes:

```yaml
paths:
  - 'new-worker/**'
  - 'commons-python/**'
  - 'schemas/**'
```

### 5. Add Makefile targets

Add `sparse-new-worker`, `test-new-worker`, `build-new-worker`, and `run-new-worker` targets.

### 6. Add k8s manifests

See [`docs/deployment.md`](docs/deployment.md) for the expected manifest structure.

### 7. Update the root README

Add the worker to the repo structure tree and any relevant tables.

---

## Code Conventions

- **Logging:** Use structured logging (JSON to stdout). All workers use Python's `logging` module with a shared formatter from `commons`.
- **Config:** All configuration via environment variables, parsed by `pydantic-settings`. No config files baked into images.
- **Error handling:** Workers must not crash on transient RabbitMQ failures. Use the retry/reconnect helpers in `commons/rabbitmq.py`.
- **Dead-letter queues:** Every queue has a corresponding DLQ. Messages that fail after max retries are routed to the DLQ. See the RabbitMQ helpers in `commons` for the convention.
- **Tests:** Minimum expectation is unit tests for all transform/business logic. Integration tests using a local RabbitMQ (via `podman compose`) are encouraged.
