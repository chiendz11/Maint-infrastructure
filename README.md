# Maint-infrastructure

Infrastructure source for MaintAI: AWS Terraform and local **k3d + Argo CD bootstrap**,
based on Iris ownership patterns. Public remote:
[chiendz11/Maint-infrastructure](https://github.com/chiendz11/Maint-infrastructure).
The AWS baseline remains1.3.1; local source locks track the reviewed app commit.
CI checks source separately from image builds, provisioning and deployment.

```text
terraform/bootstrap/     encrypted versioned state, GitHub OIDC and plan/apply roles
terraform/domain/        DNS zone (or existing zone) and DNS-validated wildcard ACM
terraform/platform/      VPC/EKS/RDS/S3/SQS/DynamoDB/ECR/IAM and non-secret outputs
terraform/argocd/        Argo CD Helm release and separately gated root Application
contracts/              platform-contract-v2 consumed by MaintAI-gitops
scripts/                explicit plan/apply runner, allow-list exporter, handoff
.github/workflows/      source CI, opt-in plan/apply and platform handoff
.github/rulesets/       main protection as code; not applied to GitHub
versions/               contract SHA locks
```

Read [architecture](docs/ARCHITECTURE.md), [bootstrap](docs/BOOTSTRAP.md),
[platform contract](docs/PLATFORM_CONTRACT.md), [versioning](docs/VERSIONING.md),
[security](docs/SECURITY.md) and [provenance](docs/reference-lock.json).

Terraform owns cloud resources and Argo bootstrap. In-cluster apps/add-ons belong
to `../MaintAI-gitops`; its public remote is
[chiendz11/MaintAI-gitops](https://github.com/chiendz11/MaintAI-gitops).
Exact provider pins/checksum locks are present; addon
builds, AMI release, PostgreSQL/pgvector minor, domain and account-specific inputs
must be supplied before any future plan. `enable_gitops_root=false` by default.

## Application alignment — PROC-ORDER-01,2026-10-23

The current app design is [v1.4 + PROC-ORDER-01](../MaintAI/docs/PROCESSING_CONCURRENCY_AND_ORDERING.md),
with [SDK0.2/bundle1.1 implementation evidence](../MaintAI/docs/PROCESSING_ORDERING_IMPLEMENTATION_REPORT.md).
This supplements the existing platform1.3.1 baseline; it is not a full platform
migration or deployment. Keyed queues/offset coordinator stay inside Worker;
ordered key cursor stays with Relay. No new workload/database/UI is introduced.
All image/enablement/cloud gates remain as configured; real callbacks, owner DB
activation and image/runtime/config review are still required.

## Local development — k3d + Argo CD (1.0.0)

Local development is now part of these two platform repositories. Infrastructure
bootstraps the cluster/private kubeconfig/secrets/Argo CD; GitOps owns local
platform and app desired state. AWS production sources remain independently
versioned. Local implementation/CI is authored but not executed or deployed.

Start with [local runbook](local/README.md).

See [source synchronization and publication](docs/LOCAL_SOURCE_SYNC.md) for the
current app lock, public GitOps URL and remaining demo runtime inputs.
