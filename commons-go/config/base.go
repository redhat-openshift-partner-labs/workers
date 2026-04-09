// Package config provides shared configuration primitives for Go workers.
// Workers embed BaseRabbitMQConfig in their own settings struct and use
// github.com/caarlos0/env to parse environment variables with a worker-specific
// prefix (e.g. env.ParseWithOptions(s, env.Options{Prefix: "SCRIBE_"})).
package config

// BaseRabbitMQConfig holds the standard RabbitMQ connection parameters that
// every worker needs. Embed this in your worker's Settings struct.
//
// With a prefix of "SCRIBE_", the resolved env var names become:
//
//	SCRIBE_RABBITMQ_HOST
//	SCRIBE_RABBITMQ_PORT
//	SCRIBE_RABBITMQ_USER
//	SCRIBE_RABBITMQ_PASSWORD
//	SCRIBE_RABBITMQ_VHOST
type BaseRabbitMQConfig struct {
	RabbitMQHost     string `env:"RABBITMQ_HOST" envDefault:"localhost"`
	RabbitMQPort     int    `env:"RABBITMQ_PORT" envDefault:"5672"`
	RabbitMQUser     string `env:"RABBITMQ_USER" envDefault:"guest"`
	RabbitMQPassword string `env:"RABBITMQ_PASSWORD" envDefault:"guest"`
	RabbitMQVHost    string `env:"RABBITMQ_VHOST" envDefault:"/"`
}