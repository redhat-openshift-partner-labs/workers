// Package config holds the scribe worker's configuration.
// All values are read from environment variables at startup with the
// SCRIBE_ prefix (e.g. SCRIBE_RABBITMQ_HOST, SCRIBE_DATABASE_URL).
package config

import (
	"github.com/caarlos0/env/v11"
	"github.com/redhat-openshift-partner-labs/workers/commons-go/config"
)

// Settings is the complete configuration for the scribe worker.
// Embed BaseRabbitMQConfig to inherit the standard RabbitMQ fields;
// all fields are read with the SCRIBE_ prefix applied by Parse.
type Settings struct {
	config.BaseRabbitMQConfig

	// DatabaseURL is the full PostgreSQL connection string.
	// Example: postgres://user:pass@host:5432/dbname
	DatabaseURL string `env:"DATABASE_URL,required"`

	// ConsumeQueue is the queue scribe reads from.
	ConsumeQueue string `env:"CONSUME_QUEUE" envDefault:"intake.normalized"`

	// DLQQueue is the dead-letter queue for messages that fail processing.
	DLQQueue string `env:"DLQ_QUEUE" envDefault:"dlq.intake"`

	// SourceID is the identifier placed in outbound envelope Source fields.
	SourceID string `env:"SOURCE_ID" envDefault:"worker-scribe"`

	// HealthPort is the port for the /healthz and /readyz HTTP endpoints.
	HealthPort int `env:"HEALTH_PORT" envDefault:"8080"`

	// PrefetchCount controls how many unacknowledged messages the broker
	// delivers at once. Keep at 1 for fair dispatch across replicas.
	PrefetchCount int `env:"PREFETCH_COUNT" envDefault:"1"`
}

// Parse reads environment variables and returns a populated Settings.
// Returns an error if any required variable is missing.
func Parse() (*Settings, error) {
	var s Settings
	if err := env.ParseWithOptions(&s, env.Options{Prefix: "SCRIBE_"}); err != nil {
		return nil, err
	}
	return &s, nil
}
