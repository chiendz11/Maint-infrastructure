# MaintAI platform architecture

Current application design: **1.4.0 + PROC-ORDER-01/1.0.0**; see
[application decision](../../MaintAI/docs/PROCESSING_CONCURRENCY_AND_ORDERING.md) and
[implementation report](../../MaintAI/docs/PROCESSING_ORDERING_IMPLEMENTATION_REPORT.md).
Existing platform code/contract baseline: **1.3.1**. Platform architecture revision:
`maintai-1.3.1+simulator-ui.1`. Initial code delivery: 2026-10-18, **unvalidated**.

## User decision taking precedence over supplied documents

The user requested a separate Simulator UI. Its backend remains Sensor Simulator:

```text
Simulator UI -> Sensor Control API + scheduler -> Ingestion API -> Kafka
Main Frontend -> Business REST/SSE API
```

This supersedes the Business simulator-control facade in supplied Contracts 33.6,
Guide 41.2 and the app's current skeleton. The main frontend must not send control
commands or carry simulator service credentials. Simulator UI calls same-origin
`/api/v1/simulator/...`, routed by its management Ingress to Sensor port 8005.
Main application `/api` goes to Business port 8003. Sensor sends records internally
to Ingestion port 8000. There is no extra simulator backend deployment.
Pause stops generation of new readings, not accepted Kafka backlog, retries or
active alerts. Only one Sensor controller owns the machine schedules. Sensor has
one replica, durable state PVC and `Recreate`, not an overlapping rolling update.
Recreate addresses normal upgrades, not fencing under uncertain node termination.
A shared lease/leader is needed for strict ownership or any multi-controller configuration.

## Application data flow and ownership

```text
Sensor -> Ingestion -> sensor.readings
  -> Processing group -> DQ -> ML /api/v1/predict -> Risk -> processing_db + outbox
  -> Storage group -> immutable raw JSONL.gz + manifests in S3
  -> Business telemetry handler -> latest unverified telemetry in business_db

Processing outbox relay -> inference.results / alert.signals
  -> Business prediction/alert handlers -> business_db -> transactional NOTIFY
  -> every Business API replica -> SSE -> Main Frontend

Business API -> Processing read API for history, status and original alert context
Business API/background job -> RAG -> knowledge_db + LLM -> persisted brief
Drift CronJob -> Processing VALID window / curated S3 -> drift_db + S3 + Pushgateway
Approved dataset manifest -> SQS -> Argo Events -> batch training -> quality gate
  -> model release intent -> GitOps PR -> operator merge -> Argo reconciliation
```

Business keeps latest read projections, alerts, audit, feedback and briefs, not
full raw/processing history. Processing creates risk/signals; Business creates
alert IDs and owns lifecycle. LLM outages never delay alert creation.

One private RDS PostgreSQL instance has five owner databases: `processing_db`,
`business_db`, `drift_db`, `mlflow_db`, `knowledge_db`. Each owner has its own login
and migrations. No cross-owner SQL/FKs. MLflow owns its own schema; training uses
its HTTP API. RAG uses pinned pgvector in knowledge_db. RDS `postgres` is the
administrative connection database, not a sixth application data owner.

## Runtime map

| Runtime | Workload | Image group | Database |
|---|---|---|---|
| ingestion-api | Deployment | ingestion-api | none |
| processing-worker/read-api/outbox-relay | 3 Deployments | processing | processing_db |
| storage-consumer | Deployment | storage-consumer | none; raw S3 |
| business-api/business-consumer | 2 Deployments | business-backend | business_db |
| ml-service | Deployment | ml-service | none |
| rag-service | Deployment | rag-service | knowledge_db |
| frontend | Deployment | frontend | none |
| simulator-ui | Deployment | simulator-ui | none |
| sensor | single-controller Deployment | sensor | durable local PVC |
| drift-worker | CronJob | drift-worker | drift_db |
| training | Argo Workflow task | training | MLflow API only |

There are 13 application workload packages plus the training task. MLflow,
Pushgateway, Kafka and controllers are platform workloads. Shared source owners
may use one image with distinct entrypoints. Training and inference remain
separate images. MaintAI keeps its own `/api/v1/predict` protocol: Iris KServe/
Knative manifests are deliberately not copied into this design.

## Ownership between the new repositories

Terraform in `Maint-infrastructure`: state/KMS, VPC/NAT, EKS/nodes/add-ons/IRSA,
RDS, versioned S3, SQS/DLQ, DynamoDB training ledger, ECR, cloud secret metadata,
DNS/ACM, Argo CD Helm release and root Application bootstrap.

Argo CD desired state in `MaintAI-gitops`: namespaces, Strimzi/Kafka/topics/ACLs,
External Secrets, storage classes, Workflows/Events, monitoring, application
Deployments/Services/ConfigMaps, management/main Ingress and training manifests.
Argo CD does not manage its own Helm release. No resource has two owners.

## Failure/upgrade behavior

DB outcome and outbox commit before Processing offset. Relay marks published only
after broker ACK. Business inbox+projection/alert+audit commit before its offset.
Storage commits offsets after durable object+manifest. Redelivery is expected;
there is no exactly-once claim across Kafka, PostgreSQL, S3 and external ML calls.
Consumers need rebalance/shutdown handling and stable per-machine sequence CAS.
SSE reconnect uses REST resync; PG NOTIFY is not a durable replay log.

HTTP runtimes use readiness/startup/liveness and rolling maxUnavailable=0,
maxSurge=1. Consumers still rebalance on rollout. A PDB constrains voluntary
infrastructure disruptions, not data correctness. A model release restarts both
inference and drift reference consumers using one immutable model bundle.

## Explicit limits in this initial code

- App is still largely skeleton; the proposed Python module/health/env contracts
  in `config/components.json` must be implemented or reviewed in the app repo.
- Simulator UI/Sensor provider and Storage now have application source; Processing
  has SDK/wrappers. Source does not prove these platform workload entrypoints,
  health/config/image or deployed integration are reviewed.
- Current Kafka wire freeze is managed in MaintAI/contracts/kafka and the GitOps
  Kafka pin: result writer1.4.0/legacy2.0.0 reader, SDK0.2.0/bundle1.1.0. Terraform
  does not choose event versions or bypass application/config/migration gates.
- Drift report read bridge into Business and durable brief-job executor remain
  app-contract decisions. `DRIFT_READ_MODE=unconfigured` means explicit unavailable,
  not permission for Business to read drift_db or a fabricated Drift HTTP service.
- External OIDC issuer/public clients are configurable; no Auth Server is added.
  Business and Sensor must implement their permission checks and service auth.
- One NAT and default single-AZ RDS are a demo-cost profile, not production HA.
  Five logical DBs on one instance share failure/capacity. Three Kafka brokers
  still require real retention, storage, outage and catch-up sizing.
- p95 <= 2 seconds is event-to-visible-alert, not HTTP 202 latency. No benchmark,
  model score, dependency compatibility or deployment success is claimed here.

## PROC-ORDER-01 amendment — 2026-10-23

SDK0.2.0/bundle1.1.0 now implement keyed Processing, partition safe-prefix offset
coordination, durable assignment/source-cursor fencing and ordered per-topic/key
outbox dispatch. Processing transport wrappers/factory exist; real owner DQ/ML/
risk/history callbacks and health/image/deployment integration are still pending.

Scheduler/coordinator are modules inside one Processing Worker; relay/read API
remain distinct runtimes in the same owner/image group/DB. No new DB/service/UI.
Business/Storage keep serial defaults. Source sequence increases across epochs;
opaque epoch UUIDs are not sortable. Ordered dispatch does not eliminate late
physical duplicates or impose total order across topics; inbox/CAS remain needed.

Activation requires explicit owner migration002, drain of legacy writers/relays
and an evidence-based legacy cursor bootstrap if old source inbox exists. This
release refuses guessed bootstrap. Runtime key/queue/byte/deadline/pool budgets
and retention/catch-up/rolling must be measured, not inferred from12 partitions.
No new Terraform/cloud resource is required solely for this internal concurrency.

## Local environment amendment — 2026-10-29

The separate MaintAI-k3d source is a migration reference, not the new active
ownership boundary. Local infrastructure/Argo bootstrap lives in Maint-infrastructure;
local Kubernetes desired state lives in MaintAI-gitops/environments/local.
The local handoff uses actual M5 entrypoints and SDK0.3/bundle2/outcome1.4,
separate from dated production1.3.1/config2.0 snapshots above. No production
activation, wire/schema change, build, test, deployment or benchmark is implied.
