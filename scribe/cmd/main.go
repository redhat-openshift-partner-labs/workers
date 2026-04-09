// Command scribe subscribes to intake.normalized and persists each lab
// request to PostgreSQL. Run with all SCRIBE_* environment variables set.
package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/redhat-openshift-partner-labs/workers/commons-go/health"
	"github.com/redhat-openshift-partner-labs/workers/commons-go/rabbitmq"
	"github.com/redhat-openshift-partner-labs/workers/scribe/internal/config"
	"github.com/redhat-openshift-partner-labs/workers/scribe/internal/store"
	"github.com/redhat-openshift-partner-labs/workers/scribe/internal/worker"
)

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)))

	cfg, err := config.Parse()
	if err != nil {
		slog.Error("config parse failed", "error", err)
		os.Exit(1)
	}

	// ── PostgreSQL ────────────────────────────────────────────────────
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	db, err := store.New(ctx, cfg.DatabaseURL)
	if err != nil {
		slog.Error("postgres connect failed", "error", err)
		os.Exit(1)
	}
	defer db.Close()

	// ── RabbitMQ ──────────────────────────────────────────────────────
	rmq, err := rabbitmq.Dial(rabbitmq.Config{
		Host:     cfg.RabbitMQHost,
		Port:     cfg.RabbitMQPort,
		User:     cfg.RabbitMQUser,
		Password: cfg.RabbitMQPassword,
		VHost:    cfg.RabbitMQVHost,
	})
	if err != nil {
		slog.Error("rabbitmq connect failed", "error", err)
		os.Exit(1)
	}
	defer rmq.Close()

	if err := rmq.DeclareQueue(cfg.ConsumeQueue); err != nil {
		slog.Error("declare consume queue failed", "queue", cfg.ConsumeQueue, "error", err)
		os.Exit(1)
	}
	if err := rmq.DeclareQueue(cfg.DLQQueue); err != nil {
		slog.Error("declare dlq failed", "queue", cfg.DLQQueue, "error", err)
		os.Exit(1)
	}
	if err := rmq.SetPrefetch(cfg.PrefetchCount); err != nil {
		slog.Error("set prefetch failed", "error", err)
		os.Exit(1)
	}

	// ── Health server ─────────────────────────────────────────────────
	// Readiness requires both RabbitMQ and PostgreSQL to be reachable.
	hs := health.New(cfg.HealthPort, func() bool {
		return rmq.IsReady() && db.IsReady(ctx)
	})
	hs.Start()
	defer func() {
		shutCtx, shutCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer shutCancel()
		hs.Stop(shutCtx)
	}()

	slog.Info("scribe started",
		"consume_queue", cfg.ConsumeQueue,
		"dlq_queue", cfg.DLQQueue,
		"health_port", cfg.HealthPort,
	)

	// ── Signal handling ───────────────────────────────────────────────
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGTERM, syscall.SIGINT)

	w := worker.New(rmq, db, cfg.ConsumeQueue, cfg.DLQQueue, cfg.SourceID)

	// Run the consume loop in a goroutine so we can also wait for signals.
	errCh := make(chan error, 1)
	go func() {
		errCh <- w.Run(ctx)
	}()

	select {
	case sig := <-sigCh:
		slog.Info("received signal, shutting down", "signal", sig)
		cancel()
	case err := <-errCh:
		if err != nil {
			slog.Error("worker exited with error", "error", err)
			os.Exit(1)
		}
	}

	// Give in-flight handlers a moment to finish.
	time.Sleep(2 * time.Second)
}
