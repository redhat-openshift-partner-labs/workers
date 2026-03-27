"""Notification worker - RabbitMQ consumer for email notifications."""

from __future__ import annotations

import json
import logging
import signal
import sys
from typing import Any

import pika
from pika.adapters.blocking_connection import BlockingChannel

from .config import Settings
from .mailer import EmailMessage, SMTPMailer
from .templates import TemplateRenderer

logger = logging.getLogger(__name__)


class NotificationWorker:
    """RabbitMQ consumer that sends email notifications via SMTP."""

    def __init__(self, settings: Settings):
        """Initialize worker.

        Args:
            settings: Worker configuration
        """
        self.settings = settings
        self.mailer = SMTPMailer(
            host=settings.smtp_host,
            port=settings.smtp_port,
            from_addr=settings.smtp_from,
            username=settings.smtp_user,
            password=settings.smtp_pass,
            use_tls=settings.smtp_use_tls,
            max_retries=settings.max_retries,
        )
        self.renderer = TemplateRenderer(settings.template_dir)
        self.connection: pika.BlockingConnection | None = None
        self.channel: BlockingChannel | None = None
        self.should_stop = False

    def start(self) -> None:
        """Start consuming messages from RabbitMQ."""
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

        logger.info("Starting notification worker")
        logger.info(f"Consuming from queue: {self.settings.consume_queue}")
        logger.info(f"SMTP: {self.settings.smtp_host}:{self.settings.smtp_port}")

        # Connect to RabbitMQ
        params = pika.URLParameters(self.settings.rabbitmq_url)
        self.connection = pika.BlockingConnection(params)
        self.channel = self.connection.channel()

        # Declare queues
        self.channel.queue_declare(queue=self.settings.consume_queue, durable=True)
        self.channel.queue_declare(queue=self.settings.failed_queue, durable=True)

        # Set QoS
        self.channel.basic_qos(prefetch_count=self.settings.prefetch_count)

        # Start consuming
        self.channel.basic_consume(
            queue=self.settings.consume_queue,
            on_message_callback=self._on_message,
            auto_ack=False,
        )

        logger.info("Worker started. Waiting for messages...")

        try:
            self.channel.start_consuming()
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        finally:
            self._cleanup()

    def _on_message(
        self,
        channel: BlockingChannel,
        method: pika.spec.Basic.Deliver,
        properties: pika.spec.BasicProperties,
        body: bytes,
    ) -> None:
        """Handle incoming RabbitMQ message.

        Args:
            channel: RabbitMQ channel
            method: Delivery method
            properties: Message properties
            body: Message body
        """
        if self.settings.verbose:
            logger.info(f"Received message: {body.decode()}")

        try:
            # Process message
            self._process_message(body)

            # Acknowledge success
            channel.basic_ack(delivery_tag=method.delivery_tag)

            if self.settings.verbose:
                logger.info("Message processed successfully")

        except Exception as e:
            logger.error(f"Error processing message: {e}")

            # Route to failed queue
            try:
                channel.basic_publish(
                    exchange="",
                    routing_key=self.settings.failed_queue,
                    body=body,
                    properties=pika.BasicProperties(delivery_mode=2),
                )
                logger.info(f"Message routed to {self.settings.failed_queue}")
            except Exception as publish_error:
                logger.error(f"Failed to route to DLQ: {publish_error}")

            # Acknowledge (don't requeue)
            channel.basic_ack(delivery_tag=method.delivery_tag)

    def _process_message(self, body: bytes) -> None:
        """Process email notification message.

        Args:
            body: JSON message body

        Raises:
            ValueError: If message is invalid
            Exception: If email sending fails
        """
        # Parse JSON
        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}") from e

        # Validate required fields
        required_fields = ["to", "subject", "template", "data"]
        missing = [f for f in required_fields if f not in data]
        if missing:
            raise ValueError(f"Missing required fields: {missing}")

        # Extract fields
        to = data["to"]
        cc = data.get("cc")
        bcc = data.get("bcc")
        subject = data["subject"]
        template_name = data["template"]
        template_data = data["data"]

        # Validate types
        if not isinstance(to, list) or not to:
            raise ValueError("'to' must be a non-empty list")
        if not isinstance(subject, str) or not subject:
            raise ValueError("'subject' must be a non-empty string")
        if not isinstance(template_name, str) or not template_name:
            raise ValueError("'template' must be a non-empty string")
        if not isinstance(template_data, dict):
            raise ValueError("'data' must be a dictionary")

        # Render template
        try:
            body_text = self.renderer.render(template_name, template_data)
        except Exception as e:
            raise ValueError(f"Template rendering failed: {e}") from e

        # Build email message
        email = EmailMessage(
            to=to,
            cc=cc,
            bcc=bcc,
            subject=subject,
            body=body_text,
        )

        # Send email
        self.mailer.send(email)

        if self.settings.verbose:
            logger.info(f"Email sent to {to} (template: {template_name})")

    def _handle_shutdown(self, signum: int, frame: Any) -> None:
        """Handle shutdown signal.

        Args:
            signum: Signal number
            frame: Stack frame
        """
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.should_stop = True
        if self.channel:
            self.channel.stop_consuming()

    def _cleanup(self) -> None:
        """Clean up resources."""
        logger.info("Cleaning up resources...")
        if self.channel and self.channel.is_open:
            self.channel.close()
        if self.connection and self.connection.is_open:
            self.connection.close()
        logger.info("Worker stopped")


def main() -> None:
    """Entry point for notification worker."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Load settings
    try:
        settings = Settings()
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        sys.exit(1)

    # Create and start worker
    worker = NotificationWorker(settings)
    worker.start()


if __name__ == "__main__":
    main()
