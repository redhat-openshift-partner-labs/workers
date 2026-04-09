package envelope

import (
	"encoding/json"
	"time"

	"github.com/google/uuid"
)

// Envelope is the standard message wrapper for all inter-worker communication.
// Every message in the system is wrapped in this structure to carry tracing
// metadata alongside the event-specific payload.
type Envelope struct {
	EventType     string          `json:"event_type"`
	EventID       string          `json:"event_id"`
	Timestamp     time.Time       `json:"timestamp"`
	Source        string          `json:"source"`
	CorrelationID string          `json:"correlation_id"`
	CausationID   *string         `json:"causation_id"`
	Version       string          `json:"version"`
	RetryCount    int             `json:"retry_count"`
	PayloadType   *string         `json:"payload_type,omitempty"`
	Payload       json.RawMessage `json:"payload"`
}

// Build constructs a new outbound Envelope. Pass empty string for causationID
// if there is no upstream event ID to reference. A new correlationID is
// generated automatically when the provided value is empty.
func Build(eventType string, payload any, source, correlationID, causationID string) (*Envelope, error) {
	payloadJSON, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}

	corrID := correlationID
	if corrID == "" {
		corrID = uuid.New().String()
	}

	e := &Envelope{
		EventType:     eventType,
		EventID:       uuid.New().String(),
		Timestamp:     time.Now().UTC(),
		Source:        source,
		CorrelationID: corrID,
		Version:       "1.0.0",
		RetryCount:    0,
		Payload:       payloadJSON,
	}

	if causationID != "" {
		e.CausationID = &causationID
	}

	return e, nil
}

// Parse deserializes an Envelope from raw RabbitMQ message bytes.
func Parse(body []byte) (*Envelope, error) {
	var e Envelope
	if err := json.Unmarshal(body, &e); err != nil {
		return nil, err
	}
	return &e, nil
}

// ToJSON serializes the Envelope to JSON bytes for publishing.
func (e *Envelope) ToJSON() ([]byte, error) {
	return json.Marshal(e)
}

// UnmarshalPayload decodes the raw Payload field into the given target struct.
func (e *Envelope) UnmarshalPayload(v any) error {
	return json.Unmarshal(e.Payload, v)
}