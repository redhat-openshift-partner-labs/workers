from __future__ import annotations

import logging
import signal

import pika
from pydantic import ValidationError

from config import Settings
from envelope import build_envelope, parse_envelope
from health import HealthServer
from models import GenerateManifestsPayload

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger("worker-lifecycle")


class LifecycleWorker:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._connection: pika.BlockingConnection | None = None
        self._channel: pika.channel.Channel | None = None
        self._shutting_down = False
        self._connected = False

    def connect(self) -> None:
        credentials = pika.PlainCredentials(
            self.settings.rabbitmq_user,
            self.settings.rabbitmq_pass,
        )
        params = pika.ConnectionParameters(
            host=self.settings.rabbitmq_host,
            port=self.settings.rabbitmq_port,
            virtual_host=self.settings.rabbitmq_vhost,
            credentials=credentials,
            heartbeat=60,
        )
        self._connection = pika.BlockingConnection(params)
        self._channel = self._connection.channel()

        self._channel.queue_declare(queue=self.settings.consume_queue, passive=True)
        self._channel.basic_qos(prefetch_count=self.settings.prefetch_count)
        self._connected = True
        log.info(
            "Connected to RabbitMQ at %s:%s vhost=%s",
            self.settings.rabbitmq_host,
            self.settings.rabbitmq_port,
            self.settings.rabbitmq_vhost,
        )

    def _on_message(
        self,
        channel: pika.channel.Channel,
        method: pika.spec.Basic.Deliver,
        properties: pika.spec.BasicProperties,
        body: bytes,
    ) -> None:
        incoming = None
        try:
            incoming = parse_envelope(body)
            payload_data = incoming.get("payload", {})
            correlation_id = incoming.get("correlation_id")
            causation_id = incoming.get("event_id")

            log.info(
                "Received message event_id=%s correlation_id=%s",
                incoming.get("event_id"),
                correlation_id,
            )

            payload = GenerateManifestsPayload.model_validate(payload_data)

            log.info(
                "Validated payload for cluster_name=%s provider=%s",
                payload.cluster_name,
                payload.lab_config.cloud_provider,
            )

            # TODO Phase 2: generate manifests
            # TODO Phase 3: create GitHub PR

            result_payload = {
                "cluster_name": payload.cluster_name,
                "pr_url": "",
                "pr_number": 0,
                "branch_name": f"provision/{payload.cluster_name}",
                "manifests_path": f"provision/{payload.cluster_name}",
                "commit_sha": "",
                "manifests_generated": [],
            }

            msg = build_envelope(
                event_type="lab.provision.manifests-complete",
                payload=result_payload,
                source=self.settings.source_id,
                correlation_id=correlation_id,
                causation_id=causation_id,
            )
            channel.basic_publish(
                exchange=self.settings.publish_exchange,
                routing_key=self.settings.publish_routing_key,
                body=msg,
                properties=pika.BasicProperties(delivery_mode=2),
            )
            log.info("Published manifests-complete for cluster_name=%s", payload.cluster_name)

            channel.basic_ack(delivery_tag=method.delivery_tag)

        except ValidationError as e:
            log.warning("Payload validation failed: %s", e)
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

        except Exception:
            log.exception("Unexpected error processing message")
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def run(self) -> None:
        self.connect()
        self._channel.basic_consume(
            queue=self.settings.consume_queue,
            on_message_callback=self._on_message,
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

    def is_ready(self) -> bool:
        return (
            self._connected
            and self._connection is not None
            and self._connection.is_open
            and not self._shutting_down
        )

    def shutdown(self, signum, frame) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self._connected = False
        log.info("Received signal %s — stopping consumer...", signum)
        if self._channel:
            self._channel.stop_consuming()


def main() -> None:
    settings = Settings()

    worker = LifecycleWorker(settings)

    health = HealthServer(port=settings.health_port, readiness_check=worker.is_ready)
    health.start()

    signal.signal(signal.SIGTERM, worker.shutdown)
    signal.signal(signal.SIGINT, worker.shutdown)

    try:
        worker.run()
    finally:
        health.stop()


if __name__ == "__main__":
    main()
