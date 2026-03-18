"""
Environment-based configuration for the ETL worker.
All values come from env vars (12-factor), with sensible defaults for local dev.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # RabbitMQ
    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_pass: str = "guest"
    rabbitmq_vhost: str = "/"

    # Queues
    consume_queue: str = "intake.raw"
    publish_queue: str = "intake.normalized"
    failed_queue: str = "intake.raw.failed"

    # Schema configuration
    # Multi-schema: directory containing *.yaml schema files (preferred)
    schema_dir: str = "/etc/etl-schemas"
    # Default payload_type when message envelope lacks one
    default_payload_type: str = "google-sheets-v1"
    # Deprecated: single schema file path (for backward compatibility)
    # If set and schema_dir is empty/missing, falls back to this
    schema_path: str | None = None

    # Worker identity (used in message envelope `source` field)
    source_id: str = "worker-etl"

    # Prefetch — how many unacked messages to hold at once.
    # 1 = process one at a time. Safe default for correctness.
    prefetch_count: int = 1

    # Health check server port for Kubernetes probes
    health_port: int = 8080

    model_config = {"env_prefix": "ETL_"}
