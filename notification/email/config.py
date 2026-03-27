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
    rabbitmq_vhost: str = "/"

    # Queue names
    consume_queue: str = "lab.notify.email"
    failed_queue: str = "lab.notify.email.failed"

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
    template_dir: str = "templates"
    verbose: bool = False

    @property
    def rabbitmq_url(self) -> str:
        """Build RabbitMQ connection URL."""
        return (
            f"amqp://{self.rabbitmq_user}:{self.rabbitmq_pass}"
            f"@{self.rabbitmq_host}:{self.rabbitmq_port}{self.rabbitmq_vhost}"
        )
