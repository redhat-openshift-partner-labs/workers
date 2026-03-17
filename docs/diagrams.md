# Architecture Diagrams

All diagrams use [Mermaid](https://mermaid.js.org/) syntax and render natively in GitHub, VS Code, and most markdown viewers.

Key diagrams are also embedded inline in the relevant docs. This page collects them in one place.

---

## Message Flow

Scribe (saga orchestrator, separate repo) is the central routing hub. All workers publish results back to scribe, which decides the next step.

```mermaid
flowchart LR
    subgraph Intake
        N8N([n8n]) -- intake.raw --> ETL[worker-etl]
    end

    ETL -- intake.normalized --> SCRIBE((scribe))

    subgraph Dispatch
        SCRIBE -- notify / review --> MSGR([messenger])
        MSGR -- provision / review --> SCRIBE
    end

    subgraph Provisioning
        SCRIBE -- generate-manifests --> PROV[worker-provisioning]
        PROV -- manifests-complete --> SCRIBE
        PW([provision-watcher]) -- cluster-ready --> SCRIBE
    end

    subgraph Day-One
        SCRIBE -- day1.orchestrate --> D1[worker-day-one]
        D1 -- day1.complete --> SCRIBE
    end

    subgraph Handoff
        SCRIBE -- credentials.create --> CRED[worker-credentials]
        CRED -- credentials.complete --> SCRIBE
        SCRIBE -- welcome-email.send --> NOTIF[worker-notification]
        NOTIF -- welcome-email.sent --> SCRIBE
    end

    subgraph Deprovision
        SCRIBE -- deprovision.requested --> DEPROV[worker-deprovision]
        DEPROV -- archive-complete --> SCRIBE
        DW([deprovision-watcher]) -- cluster-removed --> SCRIBE
    end
```

> Workers in **rectangles** live in the workers monorepo. **Rounded boxes** are external components.
> Queue names are abbreviated — see [docs/architecture.md](architecture.md) for the full map.

---

## Dependency Graph

How workers, commons libraries, and schemas relate.

```mermaid
flowchart BT
    SCHEMAS["schemas/\n(JSON Schema — source of truth)"]

    CP["commons-python/\n(Pydantic models, RabbitMQ helpers)"]
    CG["commons-go/\n(planned)"]

    ETL[etl/]
    PROV[provisioning/]
    D1[day-one/]
    D2[day-two/]
    DEPROV[deprovision/]
    CRED[credentials/]
    NOTIF[notification/]

    CP -->|implements| SCHEMAS
    CG -.->|will implement| SCHEMAS

    ETL --> CP
    PROV --> CP
    D1 --> CP
    D2 --> CP
    DEPROV --> CP
    CRED --> CP
    NOTIF --> CP
```

> Arrows point toward dependencies. Workers never import from `schemas/` directly —
> they go through their language's commons package.

---

## CI Trigger Map

What file changes trigger which CI workflows.

```mermaid
flowchart LR
    subgraph Changed Files
        S["schemas/**"]
        C["commons-python/**"]
        W_ETL["etl/**"]
        W_PROV["provisioning/**"]
        W_D1["day-one/**"]
        W_D2["day-two/**"]
        W_DEPROV["deprovision/**"]
        W_CRED["credentials/**"]
        W_NOTIF["notification/**"]
    end

    subgraph CI Workflows
        CI_ETL[ci-etl]
        CI_PROV[ci-provisioning]
        CI_D1[ci-day-one]
        CI_D2[ci-day-two]
        CI_DEPROV[ci-deprovision]
        CI_CRED[ci-credentials]
        CI_NOTIF[ci-notification]
    end

    S --> CI_ETL & CI_PROV & CI_D1 & CI_D2 & CI_DEPROV & CI_CRED & CI_NOTIF
    C --> CI_ETL & CI_PROV & CI_D1 & CI_D2 & CI_DEPROV & CI_CRED & CI_NOTIF

    W_ETL --> CI_ETL
    W_PROV --> CI_PROV
    W_D1 --> CI_D1
    W_D2 --> CI_D2
    W_DEPROV --> CI_DEPROV
    W_CRED --> CI_CRED
    W_NOTIF --> CI_NOTIF
```

> **Key insight:** A change to `schemas/` or `commons-python/` fans out to every workflow.
> A change to a single worker directory triggers only that worker's CI.

---

## Branching & Deploy Pipeline

From feature branch to production cluster.

```mermaid
flowchart LR
    subgraph Git
        F["feature/*\nhotfix/*"] -->|PR + CI| DEV[develop]
        DEV -->|merge commit PR| MAIN[main]
        MAIN -->|git tag\netl/v1.0.0| TAG([release tag])
    end

    subgraph CI / Build
        MAIN -->|push triggers CI| BUILD[Build image\nghcr.io/org/worker:sha]
    end

    subgraph CD — Deployment Repo
        BUILD -->|bot updates image tag| DR_DEV[dev overlay]
        DR_DEV -->|manual promote| DR_STG[staging overlay]
        DR_STG -->|manual promote\n+ approval| DR_PROD[prod overlay]
    end

    subgraph Kubernetes
        DR_DEV -->|ArgoCD sync| K_DEV[dev cluster]
        DR_STG -->|ArgoCD sync| K_STG[staging cluster]
        DR_PROD -->|ArgoCD sync| K_PROD[prod cluster]
    end
```

> **Hotfix shortcut:** `hotfix/*` branches PR directly into `main`, then cherry-pick back to `develop`.
> See [CONTRIBUTING.md](../CONTRIBUTING.md) for the full PR workflow and [docs/deployment.md](deployment.md) for CD details.

---

## Lab State Machine

Every lab progresses through these states. Scribe is the single writer — only scribe transitions state.

```mermaid
stateDiagram-v2
    [*] --> intake_received
    intake_received --> intake_transforming
    intake_transforming --> intake_stored

    intake_stored --> manifests_generating : standard config
    intake_stored --> dispatch_review_requested : non-standard

    dispatch_review_requested --> manifests_generating : Provision clicked
    dispatch_review_requested --> pending_review : Review clicked
    pending_review --> manifests_generating : Provision after review
    pending_review --> rejected : Rejected

    manifests_generating --> pr_opened
    pr_opened --> pr_checks_running
    pr_checks_running --> pr_checks_passed
    pr_checks_running --> pr_checks_failed
    pr_checks_passed --> pr_merged : auto-merge (default)
    pr_checks_passed --> pending_approval : override
    pending_approval --> pr_merged
    pr_checks_failed --> failed

    pr_merged --> cluster_installing
    cluster_installing --> active : cluster ready
    cluster_installing --> failed : cluster failed

    active --> day_one_complete : all day-one tasks pass

    day_one_complete --> pending_handoff_verification
    pending_handoff_verification --> handoff_initiated : /cluster id ready
    handoff_initiated --> credentials_created
    credentials_created --> handoff_complete : welcome email sent

    active --> deprovision_pr_opened
    deprovision_pr_opened --> deprovision_pr_merged
    deprovision_pr_merged --> cluster_deprovisioning
    cluster_deprovisioning --> deprovisioned

    rejected --> [*]
    failed --> [*]
    handoff_complete --> [*]
    deprovisioned --> [*]
```

> See [docs/architecture.md](architecture.md) for the full state machine context and saga definitions.

---

## Day-One Task Dependencies

Four tasks start in parallel; downstream tasks wait for their dependencies.

```mermaid
flowchart TD
    START([lab.day1.orchestrate]) --> INSIGHTS[insights.disable]
    START --> SSL[ssl.create]
    START --> OAUTH_HUB[oauth-hub.create]
    START --> KUBEADMIN[kubeadmin.set]

    OAUTH_HUB -->|depends on| OAUTH_SPOKE[oauth-spoke.patch]
    KUBEADMIN -->|depends on| RBAC[rbac.configure]
    OAUTH_SPOKE -->|depends on| RBAC

    INSIGHTS --> COMPLETE([lab.day1.complete])
    SSL --> COMPLETE
    RBAC --> COMPLETE
```

> All tasks execute as K8s Jobs on the hub cluster, orchestrated by worker-day-one.
> `lab.day1.complete` fires only when every task succeeds.
