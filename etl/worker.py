"""
worker-etl: Stateless RabbitMQ consumer that validates and transforms
raw Google Sheet payloads into the canonical intake.normalized schema.

Follows the worker contract:
  - Stateless (no in-memory state between messages)
  - Idempotent (same message processed twice → same result)
  - Publishes status on completion (normalized) or failure (raw.failed)
  - Horizontally scalable (N replicas competing for messages)

Usage:
  python -m src.worker

Environment variables (see config.py):
  ETL_RABBITMQ_HOST, ETL_RABBITMQ_PORT, ETL_RABBITMQ_USER, etc.
"""

from __future__ import annotations

import logging
import signal
import sys

import pika

from .config import Settings
from .schema import load_schema, ETLSchema
from .transform import transform, TransformError
from .envelope import build_envelope, parse_envelope

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger("worker-etl")


class ETLWorker:
    """
    Consumes from intake.raw, transforms, publishes to intake.normalized
    or intake.raw.failed. One message at a time (prefetch=1).
    """

    def __init__(self, settings: Settings, schema: ETLSchema):
        self.settings = settings
        self.schema = schema
        self._connection: pika.BlockingConnection | None = None
        self._channel: pika.channel.Channel | None = None
        self._shutting_down = False

    def connect(self) -> None:
        """Establish RabbitMQ connection and declare queues."""
        credentials = pika.PlainCredentials(
            self.settings.rabbitmq_user,
            self.settings.rabbitmq_pass,
        )
        params = pika.ConnectionParameters(
            host=self.settings.rabbitmq_host,
            port=self.settings.rabbitmq_port,
            virtual_host=self.settings.rabbitmq_vhost,
            credentials=credentials,
            # Heartbeat keeps the connection alive during long-ish transforms
            heartbeat=60,
        )
        self._connection = pika.BlockingConnection(params)
        self._channel = self._connection.channel()

        # Declare queues idempotently (durable = survives broker restart)
        for queue in (
            self.settings.consume_queue,
            self.settings.publish_queue,
            self.settings.failed_queue,
        ):
            self._channel.queue_declare(queue=queue, durable=True)

        # Process one message at a time — simple, correct, scalable via replicas
        self._channel.basic_qos(prefetch_count=self.settings.prefetch_count)
        log.info("Connected to RabbitMQ at %s:%s", self.settings.rabbitmq_host, self.settings.rabbitmq_port)

    def _on_message(
        self,
        channel: pika.channel.Channel,
        method: pika.spec.Basic.Deliver,
        properties: pika.spec.BasicProperties,
        body: bytes,
    ) -> None:
        """
        Callback for each message from intake.raw.

        Flow:
          1. Parse the envelope
          2. Extract the raw payload (AppScript body)
          3. Run the transform pipeline
          4. Publish normalized payload or failure
          5. ACK the original message (always — failures go to failed queue, not redelivered)
        """
        incoming = None
        try:
            incoming = parse_envelope(body)
            payload = incoming.get("payload", {})
            correlation_id = incoming.get("correlation_id")
            causation_id = incoming.get("event_id")  # This message caused the next one

            # The raw payload has form_response_id and sheet_row from the intake.raw schema
            raw_body = payload.get("sheet_row", payload)
            form_response_id = payload.get("form_response_id", "unknown")
            sheet_row_number = payload.get("sheet_row_number")

            log.info(
                "Processing form_response_id=%s row=%s",
                form_response_id,
                sheet_row_number,
            )

            # ── Transform ─────────────────────────────────────────────
            result = transform(self.schema, raw_body)

            # ── Build normalized payload ──────────────────────────────
            normalized_payload = {
                "form_response_id": form_response_id,
                "sheet_row_number": sheet_row_number,
                "cluster_name": result["db_columns"].get("cluster_name", ""),
                "cluster_id": result["db_columns"].get("cluster_id", ""),
                "generated_name": result["db_columns"].get("generated_name", ""),
                "base_domain": "",  # Not in Sheet — set downstream or via config
                "hub_cluster_name": "",  # Set downstream or via config
                "hub_base_domain": "",  # Set downstream or via config
                "requester": {
                    "email": result["db_columns"].get("primary_email", ""),
                    "name": f"{result['db_columns'].get('primary_first', '')} {result['db_columns'].get('primary_last', '')}".strip(),
                },
                "users": self._build_users_list(result["db_columns"]),
                "lab_config": {
                    "openshift_version": result["db_columns"].get("openshift_version", ""),
                    "cloud_provider": result["db_columns"].get("cloud_provider", "aws"),
                    "region": result["db_columns"].get("region", ""),
                    "cluster_size": result["db_columns"].get("cluster_size", ""),
                    "request_type": result["db_columns"].get("request_type", ""),
                    "lease_time": result["db_columns"].get("lease_time", ""),
                },
                "special_requests": result["db_columns"].get("notes", ""),
                "is_standard_config": result["is_standard_config"],
                # Full DB-ready data for Scribe to persist directly
                "db_columns": result["db_columns"],
                "extras": result["extras"],
            }

            # ── Publish to intake.normalized ───────────────────────────
            msg = build_envelope(
                event_type="intake.normalized",
                payload=normalized_payload,
                source=self.settings.source_id,
                correlation_id=correlation_id,
                causation_id=causation_id,
            )
            channel.basic_publish(
                exchange="",
                routing_key=self.settings.publish_queue,
                body=msg,
                properties=pika.BasicProperties(delivery_mode=2),  # persistent
            )
            log.info("Published normalized payload for cluster_name=%s", normalized_payload["cluster_name"])

        except TransformError as e:
            # Structured validation failure — publish to failed queue
            log.warning("Transform failed: %s — %s", e.code, e.message)
            self._publish_failure(
                channel=channel,
                error=e.to_dict(),
                raw_payload=incoming.get("payload", {}) if incoming else {},
                correlation_id=incoming.get("correlation_id") if incoming else None,
                causation_id=incoming.get("event_id") if incoming else None,
            )

        except Exception as e:
            # Unexpected error — still publish to failed queue, don't lose the message
            log.exception("Unexpected error processing message")
            self._publish_failure(
                channel=channel,
                error={"code": "UNEXPECTED_ERROR", "message": str(e)},
                raw_payload=incoming.get("payload", {}) if incoming else {},
                correlation_id=incoming.get("correlation_id") if incoming else None,
                causation_id=incoming.get("event_id") if incoming else None,
            )

        finally:
            # Always ACK — failures are routed to the failed queue, not redelivered.
            # This prevents poison messages from blocking the queue.
            channel.basic_ack(delivery_tag=method.delivery_tag)

    def _build_users_list(self, db_cols: dict) -> list[dict]:
        """Build the users array from primary + secondary contacts."""
        users = []

        primary_email = db_cols.get("primary_email", "")
        if primary_email:
            users.append({
                "email": primary_email,
                "name": f"{db_cols.get('primary_first', '')} {db_cols.get('primary_last', '')}".strip(),
                "role": "admin",
            })

        secondary_email = db_cols.get("secondary_email", "")
        if secondary_email:
            users.append({
                "email": secondary_email,
                "name": f"{db_cols.get('secondary_first', '')} {db_cols.get('secondary_last', '')}".strip(),
                "role": "user",
            })

        return users

    def _publish_failure(
        self,
        channel: pika.channel.Channel,
        error: dict,
        raw_payload: dict,
        correlation_id: str | None,
        causation_id: str | None,
    ) -> None:
        """Publish a structured failure message to intake.raw.failed."""
        failure_payload = {
            "form_response_id": raw_payload.get("form_response_id", "unknown"),
            "sheet_row_number": raw_payload.get("sheet_row_number"),
            "error": {
                **error,
                "raw_row": raw_payload.get("sheet_row", raw_payload),
            },
        }
        msg = build_envelope(
            event_type="intake.raw.failed",
            payload=failure_payload,
            source=self.settings.source_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
        channel.basic_publish(
            exchange="",
            routing_key=self.settings.failed_queue,
            body=msg,
            properties=pika.BasicProperties(delivery_mode=2),
        )

    def run(self) -> None:
        """Start consuming. Blocks until shutdown signal."""
        self.connect()
        self._channel.basic_consume(
            queue=self.settings.consume_queue,
            on_message_callback=self._on_message,
            # auto_ack=False — we ACK manually after processing
        )
        log.info("Consuming from %s — waiting for messages...", self.settings.consume_queue)
        try:
            self._channel.start_consuming()
        except KeyboardInterrupt:
            log.info("Shutting down gracefully...")
            self._channel.stop_consuming()
        finally:
            if self._connection and self._connection.is_open:
                self._connection.close()

    def shutdown(self, signum, frame) -> None:
        """Handle SIGTERM/SIGINT for graceful pod termination."""
        if self._shutting_down:
            return
        self._shutting_down = True
        log.info("Received signal %s — stopping consumer...", signum)
        if self._channel:
            self._channel.stop_consuming()


def main() -> None:
    settings = Settings()

    log.info("Loading schema from %s", settings.schema_path)
    schema = load_schema(settings.schema_path)
    log.info("Schema v%s loaded — %d fields, %d generated", schema.version, len(schema.fields), len(schema.generated_fields))

    worker = ETLWorker(settings, schema)

    # Graceful shutdown on SIGTERM (k8s pod termination) and SIGINT (ctrl+c)
    signal.signal(signal.SIGTERM, worker.shutdown)
    signal.signal(signal.SIGINT, worker.shutdown)

    worker.run()


if __name__ == "__main__":
    main()
