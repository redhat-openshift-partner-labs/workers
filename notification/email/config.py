"""Configuration for notification worker using pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Notification worker settings from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="NOTIFICATION_",
        case_sensitive=False,
    )

    # RabbitMQ connection
    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_pass: str = "guest"
    rabbitmq_vhost: str = "opl"

    # Queue configuration
    # Comma-separated list of queues to consume from
    consume_queues: str = "notify.user.lab-ready"

    # Exchange for publishing results
    publish_exchange: str = "opl.notify"
    success_routing_key: str = "notification.sent"
    failure_routing_key: str = "notification.failed"

    # SMTP settings
    smtp_host: str
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str
    smtp_use_tls: bool = True

    # Worker settings
    prefetch_count: int = 1
    max_retries: int = 3
    template_dir: str = "notification/templates"
    verbose: bool = False

    @property
    def rabbitmq_url(self) -> str:
        """Build RabbitMQ connection URL."""
        vhost = self.rabbitmq_vhost if self.rabbitmq_vhost.startswith("/") else f"/{self.rabbitmq_vhost}"
        return (
            f"amqp://{self.rabbitmq_user}:{self.rabbitmq_pass}"
            f"@{self.rabbitmq_host}:{self.rabbitmq_port}{vhost}"
        )

    @property
    def queue_list(self) -> list[str]:
        """Parse consume_queues into a list."""
        return [q.strip() for q in self.consume_queues.split(",") if q.strip()]
