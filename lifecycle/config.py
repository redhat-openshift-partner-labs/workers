from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_pass: str = "guest"
    rabbitmq_vhost: str = "opl"

    consume_queue: str = "lab.provision.generate-manifests"
    publish_exchange: str = "opl.provision"
    publish_routing_key: str = "lab.provision.manifests-complete"

    source_id: str = "worker-lifecycle"
    prefetch_count: int = 1
    health_port: int = 8080

    github_token: str = ""
    fleet_repo: str = "redhat-openshift-partner-labs/fleet-clusters"
    fleet_branch: str = "main"

    model_config = {"env_prefix": "LIFECYCLE_"}
