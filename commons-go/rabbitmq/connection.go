// Package rabbitmq provides a thin RabbitMQ connection wrapper for workers.
// It handles dialing, channel setup, queue declaration, and the basic
// publish/consume operations that every worker needs.
package rabbitmq

import (
	"fmt"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"
)

// Config holds the parameters needed to connect to RabbitMQ.
type Config struct {
	Host     string
	Port     int
	User     string
	Password string
	VHost    string
}

// Connection wraps an AMQP connection and its single channel. Workers use one
// channel per process; horizontal scaling is achieved via multiple replicas
// with prefetch=1 rather than multiple channels in one process.
type Connection struct {
	conn *amqp.Connection
	ch   *amqp.Channel
}

// Dial establishes a connection to RabbitMQ and opens a channel.
func Dial(cfg Config) (*Connection, error) {
	vhost := cfg.VHost
	if vhost == "/" {
		vhost = ""
	}
	url := fmt.Sprintf("amqp://%s:%s@%s:%d/%s",
		cfg.User, cfg.Password, cfg.Host, cfg.Port, vhost)

	conn, err := amqp.DialConfig(url, amqp.Config{
		Heartbeat: 60 * time.Second,
	})
	if err != nil {
		return nil, fmt.Errorf("dial rabbitmq: %w", err)
	}

	ch, err := conn.Channel()
	if err != nil {
		conn.Close()
		return nil, fmt.Errorf("open channel: %w", err)
	}

	return &Connection{conn: conn, ch: ch}, nil
}

// DeclareQueue ensures the named durable queue exists. Safe to call for queues
// that already exist. Call this for every queue the worker reads from or writes
// to before starting to consume or publish.
func (c *Connection) DeclareQueue(name string) error {
	_, err := c.ch.QueueDeclare(
		name,  // name
		true,  // durable
		false, // auto-delete
		false, // exclusive
		false, // no-wait
		nil,   // args
	)
	if err != nil {
		return fmt.Errorf("declare queue %q: %w", name, err)
	}
	return nil
}

// SetPrefetch limits the number of unacknowledged messages this channel will
// receive at once. Use prefetch=1 for fair dispatch across replicas.
func (c *Connection) SetPrefetch(count int) error {
	return c.ch.Qos(count, 0, false)
}

// Publish sends a message to the named queue. Messages are marked persistent
// so they survive broker restarts.
func (c *Connection) Publish(queue string, body []byte) error {
	return c.ch.Publish(
		"",    // default exchange
		queue, // routing key = queue name
		false, // mandatory
		false, // immediate
		amqp.Publishing{
			ContentType:  "application/json",
			DeliveryMode: amqp.Persistent,
			Body:         body,
		},
	)
}

// Consume begins delivering messages from the named queue. The returned channel
// is closed when the connection drops. Pass an empty consumer tag to let the
// broker assign one.
func (c *Connection) Consume(queue, consumerTag string) (<-chan amqp.Delivery, error) {
	msgs, err := c.ch.Consume(
		queue,       // queue
		consumerTag, // consumer tag
		false,       // auto-ack (we ack manually after processing)
		false,       // exclusive
		false,       // no-local
		false,       // no-wait
		nil,         // args
	)
	if err != nil {
		return nil, fmt.Errorf("consume %q: %w", queue, err)
	}
	return msgs, nil
}

// IsReady reports whether the connection is currently open.
func (c *Connection) IsReady() bool {
	return c.conn != nil && !c.conn.IsClosed()
}

// Close shuts down the channel and connection.
func (c *Connection) Close() {
	if c.ch != nil {
		c.ch.Close()
	}
	if c.conn != nil {
		c.conn.Close()
	}
}
