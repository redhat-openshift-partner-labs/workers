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

    # Schema ConfigMap path (mounted as a volume in k8s)
    schema_path: str = "/etc/etl-schema/schema.yaml"

    # Worker identity (used in message envelope `source` field)
    source_id: str = "worker-etl"

    # Prefetch — how many unacked messages to hold at once.
    # 1 = process one at a time. Safe default for correctness.
    prefetch_count: int = 1

    model_config = {"env_prefix": "ETL_"}
