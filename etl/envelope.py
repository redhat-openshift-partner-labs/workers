"""
Message envelope construction following the commons MessageEnvelope contract.
Every message on the broker uses this envelope.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone


def build_envelope(
    event_type: str,
    payload: dict,
    source: str,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    version: str = "1.0.0",
    retry_count: int = 0,
) -> bytes:
    """Build a MessageEnvelope and serialize to JSON bytes for RabbitMQ."""
    envelope = {
        "event_type": event_type,
        "event_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "correlation_id": correlation_id or str(uuid.uuid4()),
        "causation_id": causation_id,
        "version": version,
        "retry_count": retry_count,
        "payload": payload,
    }
    return json.dumps(envelope, default=str).encode("utf-8")


def parse_envelope(body: bytes) -> dict:
    """Parse a MessageEnvelope from RabbitMQ message body."""
    return json.loads(body)
