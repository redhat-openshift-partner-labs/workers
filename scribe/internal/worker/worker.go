// Package worker implements the scribe consume loop.
// It reads intake.normalized messages, resolves the company, inserts
// the lab row, and ACKs each delivery. Failures are routed to the DLQ.
package worker

import (
	"context"
	"log/slog"

	amqp "github.com/rabbitmq/amqp091-go"
	"github.com/redhat-openshift-partner-labs/workers/commons-go/envelope"
	"github.com/redhat-openshift-partner-labs/workers/commons-go/rabbitmq"
	"github.com/redhat-openshift-partner-labs/workers/scribe/internal/payload"
	"github.com/redhat-openshift-partner-labs/workers/scribe/internal/store"
)

// Worker wires together the RabbitMQ connection and the database store.
type Worker struct {
	conn         *rabbitmq.Connection
	store        *store.Store
	consumeQueue string
	dlqQueue     string
	sourceID     string
}

// New creates a Worker. The caller is responsible for declaring queues
// and setting prefetch on conn before calling Run.
func New(conn *rabbitmq.Connection, st *store.Store, consumeQueue, dlqQueue, sourceID string) *Worker {
	return &Worker{
		conn:         conn,
		store:        st,
		consumeQueue: consumeQueue,
		dlqQueue:     dlqQueue,
		sourceID:     sourceID,
	}
}

// Run starts consuming from the configured queue and blocks until ctx
// is cancelled or the delivery channel closes (connection drop).
func (w *Worker) Run(ctx context.Context) error {
	msgs, err := w.conn.Consume(w.consumeQueue, "")
	if err != nil {
		return err
	}

	slog.Info("scribe listening", "queue", w.consumeQueue)

	for {
		select {
		case <-ctx.Done():
			slog.Info("scribe shutting down")
			return nil
		case d, ok := <-msgs:
			if !ok {
				slog.Warn("delivery channel closed — connection dropped")
				return nil
			}
			w.handle(ctx, d)
		}
	}
}

// handle processes a single delivery. It always ACKs — failures are
// forwarded to the DLQ rather than requeued, preventing poison messages
// from blocking the queue indefinitely.
func (w *Worker) handle(ctx context.Context, d amqp.Delivery) {
	env, err := envelope.Parse(d.Body)
	if err != nil {
		slog.Error("failed to parse envelope", "error", err)
		w.nackToDLQ(d, d.Body, "PARSE_ENVELOPE_FAILED", err.Error())
		return
	}

	log := slog.With(
		"event_type", env.EventType,
		"event_id", env.EventID,
		"correlation_id", env.CorrelationID,
	)

	var p payload.NormalizedPayload
	if err := env.UnmarshalPayload(&p); err != nil {
		log.Error("failed to unmarshal payload", "error", err)
		w.nackToDLQ(d, d.Body, "UNMARSHAL_PAYLOAD_FAILED", err.Error())
		return
	}

	companyName := p.CompanyName()
	if companyName == "" {
		log.Error("payload missing company_name")
		w.nackToDLQ(d, d.Body, "MISSING_COMPANY_NAME", "company_name is required")
		return
	}

	companyID, err := w.store.EnsureCompany(ctx, companyName)
	if err != nil {
		log.Error("failed to ensure company", "company_name", companyName, "error", err)
		w.nackToDLQ(d, d.Body, "ENSURE_COMPANY_FAILED", err.Error())
		return
	}

	labID, err := w.store.InsertLab(ctx, &p, &companyID)
	if err != nil {
		log.Error("failed to insert lab", "error", err)
		w.nackToDLQ(d, d.Body, "INSERT_LAB_FAILED", err.Error())
		return
	}

	log.Info("lab stored", "lab_id", labID, "company_id", companyID, "company_name", companyName)

	if err := d.Ack(false); err != nil {
		log.Error("ack failed", "error", err)
	}
}

// nackToDLQ publishes a failure envelope to the DLQ and ACKs the
// original delivery. We always ACK so the original message is removed
// from the source queue regardless of DLQ publish success.
func (w *Worker) nackToDLQ(d amqp.Delivery, originalBody []byte, code, message string) {
	dlqPayload := map[string]any{
		"code":          code,
		"message":       message,
		"original_body": string(originalBody),
	}

	env, err := envelope.Build("intake.failed", dlqPayload, w.sourceID, "", "")
	if err == nil {
		body, err := env.ToJSON()
		if err == nil {
			if pubErr := w.conn.Publish(w.dlqQueue, body); pubErr != nil {
				slog.Error("failed to publish to DLQ", "dlq", w.dlqQueue, "error", pubErr)
			}
		}
	}

	if err := d.Ack(false); err != nil {
		slog.Error("ack (post-DLQ) failed", "error", err)
	}
}

