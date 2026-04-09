# Go Workers Guide

Reference for building, running, and extending Go workers in this monorepo. The `scribe` worker is the canonical implementation — read it alongside this guide.

---

## When to Write a Go Worker

Python workers (`etl/`, `notification/`) are fine for transform-heavy, schema-driven work. Prefer Go when you need:

- Statically-typed message handling without runtime surprises
- Low memory footprint on a constrained cluster
- Direct database access without an ORM
- A worker that other Go services will reference as a library dependency

---

## Repository Layout

```
workers/
├── go.work                  # Go workspace linking all Go modules
├── commons-go/              # Shared Go library — use this, don't duplicate
│   ├── go.mod
│   ├── config/base.go       # BaseRabbitMQConfig for embedding
│   ├── envelope/envelope.go # Message envelope build/parse
│   ├── health/server.go     # /healthz + /readyz HTTP server
│   └── rabbitmq/connection.go
└── scribe/                  # Reference Go worker implementation
    ├── go.mod
    ├── Containerfile
    ├── cmd/main.go          # Entry point
    ├── deploy/base/         # Kustomize manifests
    └── internal/
        ├── config/settings.go
        ├── payload/         # Message-specific types
        ├── store/           # Database layer
        └── worker/worker.go # Consume loop
```

New workers follow the same layout. Replace `scribe` with your worker name.

---

## Creating a New Go Worker

### 1. Scaffold the module

```bash
mkdir my-worker
cat > my-worker/go.mod <<'EOF'
module github.com/redhat-openshift-partner-labs/workers/my-worker

go 1.26

require (
    github.com/caarlos0/env/v11 v11.3.1
    github.com/rabbitmq/amqp091-go v1.10.0
)

require github.com/redhat-openshift-partner-labs/workers/commons-go v0.0.0

replace github.com/redhat-openshift-partner-labs/workers/commons-go => ../commons-go
EOF
```

### 2. Register in the workspace

Add your module to `go.work` at the repo root:

```
use (
    ./commons-go
    ./scribe
    ./my-worker    # add this
)
```

The `replace` directive in `go.mod` and the `use` directive in `go.work` together allow the workspace build to resolve `commons-go` locally without a VCS tag. Both are required.

### 3. Generate go.sum

```bash
go mod tidy -C my-worker
```

### 4. Create the internal structure

```
my-worker/
├── cmd/main.go
├── internal/
│   ├── config/settings.go
│   ├── payload/<event-name>.go
│   ├── store/          (if the worker writes to PostgreSQL)
│   └── worker/worker.go
├── deploy/base/
│   ├── kustomization.yaml
│   └── deployment.yaml
└── Containerfile
```

---

## commons-go Packages

Import path: `github.com/redhat-openshift-partner-labs/workers/commons-go/<pkg>`

### `config`

Provides `BaseRabbitMQConfig` — embed it in your `Settings` struct and all standard RabbitMQ fields are covered.

```go
type Settings struct {
    config.BaseRabbitMQConfig

    ConsumeQueue string `env:"CONSUME_QUEUE" envDefault:"my-queue"`
    // worker-specific fields...
}

func Parse() (*Settings, error) {
    var s Settings
    if err := env.ParseWithOptions(&s, env.Options{Prefix: "MYWORKER_"}); err != nil {
        return nil, err
    }
    return &s, nil
}
```

Resolved env var names become `MYWORKER_RABBITMQ_HOST`, `MYWORKER_RABBITMQ_PORT`, etc.

### `envelope`

All inter-worker messages use the standard envelope. Never publish raw payloads.

```go
// Consuming — parse an inbound delivery
env, err := envelope.Parse(delivery.Body)
var myPayload MyPayload
env.UnmarshalPayload(&myPayload)

// Publishing — build an outbound envelope
env, err := envelope.Build(
    "my-event.type",   // event_type
    myPayload,         // anything json.Marshal can handle
    "worker-my-name",  // source
    inboundEnv.CorrelationID,  // propagate from inbound
    inboundEnv.EventID,        // causation_id = inbound event_id
)
body, _ := env.ToJSON()
conn.Publish("target-queue", body)
```

Always propagate `correlation_id` from the inbound envelope. Set `causation_id` to the inbound `event_id`. This maintains the full message lineage for tracing.

### `rabbitmq`

```go
conn, err := rabbitmq.Dial(rabbitmq.Config{
    Host:     cfg.RabbitMQHost,
    Port:     cfg.RabbitMQPort,
    User:     cfg.RabbitMQUser,
    Password: cfg.RabbitMQPassword,
    VHost:    cfg.RabbitMQVHost,
})
defer conn.Close()

conn.DeclareQueue("my-queue")       // idempotent — call for every queue used
conn.DeclareQueue("dlq.my-domain")
conn.SetPrefetch(1)                  // always 1 for fair dispatch

msgs, _ := conn.Consume("my-queue", "")
conn.Publish("target-queue", body)
conn.IsReady()  // use in the readiness probe
```

### `health`

```go
hs := health.New(cfg.HealthPort, func() bool {
    return conn.IsReady() && db.IsReady(ctx)  // all connections must be up
})
hs.Start()
defer hs.Stop(shutdownCtx)
```

`/healthz` always returns 200. `/readyz` calls your callback — return `true` only when the worker is fully connected and ready to process messages.

---

## Config Pattern

Use `github.com/caarlos0/env/v11` with a worker-specific prefix. Every config value comes from environment variables — no config files, no Viper.

```go
type Settings struct {
    config.BaseRabbitMQConfig

    DatabaseURL   string `env:"DATABASE_URL,required"`
    ConsumeQueue  string `env:"CONSUME_QUEUE"  envDefault:"my-queue"`
    DLQQueue      string `env:"DLQ_QUEUE"      envDefault:"dlq.my-domain"`
    SourceID      string `env:"SOURCE_ID"      envDefault:"worker-my-name"`
    HealthPort    int    `env:"HEALTH_PORT"    envDefault:"8080"`
    PrefetchCount int    `env:"PREFETCH_COUNT" envDefault:"1"`
}
```

Parse with `env.ParseWithOptions(&s, env.Options{Prefix: "MYWORKER_"})`. All resolved variable names are then `MYWORKER_<FIELD>`.

---

## Consume Loop Pattern

Copy this structure for every worker. The key invariants:

- **Always ACK.** Failures go to the DLQ, never requeued. Requeueing poison messages blocks the queue for all replicas.
- **ctx.Done() stops the loop.** The main goroutine cancels the context on SIGTERM/SIGINT.
- **Log with envelope fields.** Always include `event_type`, `event_id`, `correlation_id` in your structured logger.

```go
func (w *Worker) Run(ctx context.Context) error {
    msgs, err := w.conn.Consume(w.consumeQueue, "")
    if err != nil {
        return err
    }

    for {
        select {
        case <-ctx.Done():
            return nil
        case d, ok := <-msgs:
            if !ok {
                return nil  // connection dropped — let main reconnect or exit
            }
            w.handle(ctx, d)
        }
    }
}

func (w *Worker) handle(ctx context.Context, d amqp.Delivery) {
    env, err := envelope.Parse(d.Body)
    if err != nil {
        w.nackToDLQ(d, d.Body, "PARSE_ENVELOPE_FAILED", err.Error())
        return
    }

    log := slog.With("event_id", env.EventID, "correlation_id", env.CorrelationID)

    var p MyPayload
    if err := env.UnmarshalPayload(&p); err != nil {
        log.Error("unmarshal failed", "error", err)
        w.nackToDLQ(d, d.Body, "UNMARSHAL_PAYLOAD_FAILED", err.Error())
        return
    }

    if err := w.doWork(ctx, env, &p); err != nil {
        log.Error("processing failed", "error", err)
        w.nackToDLQ(d, d.Body, "PROCESSING_FAILED", err.Error())
        return
    }

    d.Ack(false)
}
```

### DLQ routing

```go
func (w *Worker) nackToDLQ(d amqp.Delivery, originalBody []byte, code, message string) {
    dlqPayload := map[string]any{
        "code":          code,
        "message":       message,
        "original_body": string(originalBody),
    }
    env, _ := envelope.Build("my-domain.failed", dlqPayload, w.sourceID, "", "")
    body, _ := env.ToJSON()
    w.conn.Publish(w.dlqQueue, body)
    d.Ack(false)  // ACK the original regardless of DLQ publish success
}
```

Error codes follow `SCREAMING_SNAKE_CASE` — `PARSE_ENVELOPE_FAILED`, `MISSING_REQUIRED_FIELD`, etc. See naming conventions in `docs/architecture.md`.

---

## Database Access (PostgreSQL)

Workers that write to the database use `pgx/v5` directly — no ORM.

```go
// store/db.go
type Store struct{ pool *pgxpool.Pool }

func New(ctx context.Context, connString string) (*Store, error) {
    pool, err := pgxpool.New(ctx, connString)
    if err != nil { return nil, err }
    if err := pool.Ping(ctx); err != nil { pool.Close(); return nil, err }
    return &Store{pool: pool}, nil
}

func (s *Store) IsReady(ctx context.Context) bool { return s.pool.Ping(ctx) == nil }
func (s *Store) Close() { s.pool.Close() }
```

Keep each table's operations in its own file (`store/labs.go`, `store/companies.go`). Write named `const` SQL strings — no string interpolation near user data.

### Nullable columns

```go
// Use *string for nullable text columns — pgx maps nil to SQL NULL
func nullableString(s string) *string {
    if s == "" { return nil }
    return &s
}
```

### updated_at with no database default

Several tables (`public.labs`, `public.companies`, etc.) have `updated_at NOT NULL` with no `DEFAULT`. Always supply it explicitly:

```go
pool.QueryRow(ctx, insertSQL, ..., time.Now().UTC())
```

### Upsert with concurrent safety

When inserting rows that have a unique constraint (e.g., `company_name`), use INSERT … ON CONFLICT DO NOTHING with a fallback SELECT to handle concurrent workers cleanly:

```go
const insertSQL = `
    INSERT INTO public.companies (company_name, updated_at)
    VALUES ($1, NOW())
    ON CONFLICT (company_name) DO NOTHING
    RETURNING id`

var id int
err := s.pool.QueryRow(ctx, insertSQL, name).Scan(&id)
if err != nil {
    // ErrNoRows means the INSERT was a no-op (conflict) — fall through to SELECT
    err = s.pool.QueryRow(ctx, `SELECT id FROM public.companies WHERE company_name = $1`, name).Scan(&id)
}
```

---

## main.go Wiring

The entry point always follows this order:

1. Parse config (exit on error — bad config is fatal at startup)
2. Connect PostgreSQL (if applicable)
3. Connect RabbitMQ
4. Declare all queues the worker reads from or writes to
5. Set prefetch
6. Start health server
7. Register signal handler (SIGTERM, SIGINT)
8. Launch consume loop in goroutine
9. Block on signal or loop error
10. Cancel context → drain in-flight handlers → exit

```go
sigCh := make(chan os.Signal, 1)
signal.Notify(sigCh, syscall.SIGTERM, syscall.SIGINT)

errCh := make(chan error, 1)
go func() { errCh <- w.Run(ctx) }()

select {
case sig := <-sigCh:
    slog.Info("shutting down", "signal", sig)
    cancel()
case err := <-errCh:
    if err != nil { slog.Error("worker error", "error", err); os.Exit(1) }
}

time.Sleep(2 * time.Second)  // allow in-flight handlers to finish
```

---

## Containerfile

Workers use a two-stage build. The builder stage must copy `go.work` and both module trees (`commons-go/` and the worker directory) so the workspace resolver can satisfy local imports without a network fetch.

```dockerfile
FROM docker.io/library/golang:1.26 AS builder

WORKDIR /workspace
COPY go.work go.work.sum* ./
COPY commons-go/ commons-go/
COPY my-worker/ my-worker/

RUN cd commons-go && go mod download
RUN cd my-worker  && go mod download

RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
    go build -trimpath -ldflags="-s -w" \
    -o /workspace/my-worker \
    ./my-worker/cmd/...

FROM registry.access.redhat.com/ubi9/ubi-minimal:latest
COPY --from=builder /workspace/my-worker /usr/local/bin/my-worker
USER 1001
ENTRYPOINT ["/usr/local/bin/my-worker"]
```

Build from the repo root (not the worker directory) so the COPY context includes `commons-go/`:

```bash
podman build -f my-worker/Containerfile -t worker-my-name .
```

`CGO_ENABLED=0` produces a fully static binary that runs on `ubi-minimal` without libc or any additional packages.

---

## Kustomize Manifests

`deploy/base/deployment.yaml` covers the standard pattern. Key points:

- All secrets come from a `<worker>-secrets` Kubernetes Secret via `secretKeyRef` — never hardcoded.
- `MYWORKER_DATABASE_URL` follows `postgres://user:pass@host:5432/dbname`.
- Liveness probe hits `/healthz`; readiness hits `/readyz`.
- `readOnlyRootFilesystem: true` and `runAsNonRoot: true` are required.
- Default resource requests: 50m CPU / 64Mi memory. Adjust for your workload.

```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 30

readinessProbe:
  httpGet:
    path: /readyz
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 10
```

---

## Logging

Use `log/slog` with JSON output. Initialise once in `main.go`:

```go
slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)))
```

Every log line from `handle()` should carry the envelope tracing fields:

```go
log := slog.With(
    "event_type",     env.EventType,
    "event_id",       env.EventID,
    "correlation_id", env.CorrelationID,
)
log.Info("lab stored", "lab_id", labID)
```

Do not log raw message bodies at INFO or above — payloads can contain PII.

---

## Local Development

```bash
# From repo root — builds using the workspace
go build ./my-worker/...
go vet   ./my-worker/...

# Run with environment overrides
MYWORKER_RABBITMQ_HOST=localhost \
MYWORKER_DATABASE_URL=postgres://portaladmin:pass@localhost:5432/opl \
go run ./my-worker/cmd/...
```

A running RabbitMQ and PostgreSQL instance are required. The worker exits immediately if either connection fails at startup — it does not retry indefinitely. Use a process supervisor or Kubernetes restart policy to handle transient broker unavailability.

---

## Testing

Go workers don't currently have a test harness. When adding tests:

- Unit-test payload parsing and store logic in isolation.
- For integration tests, use a real RabbitMQ and PostgreSQL (via `testcontainers-go` or a local instance) — don't mock the broker.
- Table-driven tests (`[]struct{ name, input, want }`) work well for payload accessor and SQL-parameter mapping coverage.
- Keep tests in `internal/` alongside the code they test; use `_test` package suffix for black-box tests.

```go
func TestEnsureCompany_ExistingCompany(t *testing.T) {
    // seed the DB, call EnsureCompany twice, assert same id returned
}
```

---

## Adding to commons-go

`commons-go` is the shared library for all Go workers. Add a package when:

- Two or more workers would independently implement the same logic.
- The abstraction is genuinely generic (not shaped by one worker's needs).

Do not add worker-specific logic to commons-go. Do not wrap libraries there unless the wrapper reduces real boilerplate across workers.

After adding a package, run `go mod tidy -C commons-go` and commit both `go.mod` and `go.sum`.

---

## Known Gotchas

**Workspace + `go mod tidy`**
Running `go mod tidy` inside a worker directory works because it traverses up to find `go.work`. However, both the `replace` directive in the worker's `go.mod` AND the `use` directive in `go.work` are needed — the workspace alone is insufficient for `go mod tidy` and the replace alone is insufficient for multi-module builds.

**`updated_at` has no DB default**
`public.labs`, `public.companies`, and several other tables have `updated_at NOT NULL` with no `DEFAULT CURRENT_TIMESTAMP`. Every INSERT and UPDATE must supply the value explicitly. Missing it produces a runtime error, not a schema error.

**Single-channel RabbitMQ connection**
`commons-go/rabbitmq` opens one channel per `Connection`. Do not call `Consume` and `Publish` concurrently on the same `Connection` without coordination — the AMQP channel is not goroutine-safe. In practice, consume happens on the main goroutine and publish happens within `handle()` (same goroutine per delivery), so this is fine with the current pattern.

**Containerfile build context**
The Docker/Podman build context must be the repo root, not the worker directory. The Containerfile relies on `COPY commons-go/` to satisfy local imports during the build stage. Building from the worker directory will fail because `commons-go/` is out of scope.

**`payload_type` is Python-only in `Build()`**
The Go `envelope.Build()` never sets `payload_type` — Go-originated envelopes omit the field entirely (`omitempty` on a nil `*string`). Only the Python `build_envelope()` accepts it as a parameter (used by the ETL worker for schema routing). This is intentional: `payload_type` is an optional hint for intra-worker routing, not a required envelope field. If a future Go worker needs it, add a `WithPayloadType(t string)` option to `commons-go/envelope` rather than adding it to `Build()`'s signature.

**Company `curated` flag**
When `curated = true` on a `public.companies` row, the `company_id` FK on `public.labs` is load-bearing — the portal and downstream workers use it to look up pre-approved company metadata. `store.EnsureCompany` handles this correctly by always returning the existing `id` on conflict rather than creating a duplicate row.
