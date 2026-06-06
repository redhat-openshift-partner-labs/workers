from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, EmailStr


class CloudProvider(str, Enum):
    aws = "aws"
    azure = "azure"
    gcp = "gcp"
    vsphere = "vsphere"


class NetworkType(str, Enum):
    ovn_kubernetes = "OVNKubernetes"
    openshift_sdn = "OpenShiftSDN"


class GitopsRepo(BaseModel):
    org: str | None = None
    repo: str | None = None
    branch: str = "main"
    base_path: str | None = None


class LabConfig(BaseModel):
    openshift_version: str | None = None
    cloud_provider: CloudProvider | None = None
    region: str | None = None
    worker_count: int | None = None
    worker_instance_type: str | None = None
    network_type: NetworkType | None = None
    ttl_hours: int | None = None


class User(BaseModel):
    email: str
    name: str | None = None
    role: Literal["admin", "user"] = "user"


class GenerateManifestsPayload(BaseModel):
    cluster_name: str
    base_domain: str
    hub_cluster_name: str
    hub_base_domain: str
    gitops_repo: GitopsRepo | None = None
    lab_config: LabConfig
    users: list[User] = []
    auto_merge: bool = True
