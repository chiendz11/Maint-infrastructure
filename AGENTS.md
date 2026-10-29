# MaintAI platform - code-first scope

User requested code only: do not run tests, builds, Terraform init/validate/plan/apply,
Kustomize/Helm render checks, Docker, AWS/Kubernetes mutations or GitHub workflows
without a later request. Read README.md, docs/ARCHITECTURE.md, docs/VERSIONING.md
and contracts/ before changing code. This initial delivery is unvalidated.

Current application target: ../MaintAI/docs/MaintAI_System_Contracts_v1_4_DEPLOYMENT_PROVENANCE.md,
revision1.4.0, sections34–42; Guide §53 and PROC-ORDER-01 apply to Processing.
Platform code/contract baseline remains1.3.1/2.0.0 until a reviewed migration. The user's 2026-10-18 decision
overrides simulator routing: a separate Simulator UI talks to Sensor Simulator
Control API; Business API/main frontend do not proxy simulator control. Record
this in docs/ARCHITECTURE.md rather than silently rewriting supplied source docs.
Terraform owns AWS/EKS and Argo CD bootstrap; GitOps owns in-cluster add-ons and
application workloads. Keep data ownership, outbox/inbox and ordering semantics.
Drift is outside the alert path and never retrains or promotes a model.
Only approved versioned dataset manifests trigger batch training. Training creates
candidates; model deployment requires a reviewed GitOps PR. No automatic merge,
cluster patching or registry champion promotion before a confirmed deployment.
Pin images by digest; S3 objects by VersionId and SHA-256. Never commit secret
values, actual datasets, Terraform state, private keys or real environment tfvars.
Do not alter ../MaintAI, the old underscore folders, or the Iris reference repos.

## PROC-ORDER-01 scope

Read ../MaintAI/docs/PROCESSING_CONCURRENCY_AND_ORDERING.md and implementation
report. SDK0.2.0/bundle1.1.0 implement internal Processing concurrency/fences and
ordered relay; there is no additional Scheduler/Coordinator Deployment or DB.
Terraform must not manage owner SQL migrations or application queue flags.
Changing replicas/concurrency does not automatically increase ML/DB capacity.
Keep platform contract2.0.0/provider pins/IAM/resources and GitOps enablement
unchanged solely for this documentation/transport amendment. Real resource
changes require measured capacity and a separately scoped infrastructure request.

## Local k3d + Argo CD — current ownership

Read local/README.md in infrastructure or docs/LOCAL_DEVELOPMENT.md in GitOps,
plus the local contract/catalog/source locks before local changes. The current
user authorized implementation in both platform repositories. Infrastructure
owns cluster/private kubeconfig/secrets/Argo bootstrap; GitOps owns local platform
and application desired state. Do not apply the same workload from both owners.
Local pins/contracts are separate from frozen AWS/production state. SDK0.3.0,
bundle2.0.0 and native outcome1.4.0 are authoritative for this local handoff; the
older SDK/legacy-reader paragraphs are historical production baselines.
Keep all app profiles disabled until real image receipts, artifacts/auth and owner
operations are reviewed. Adapter sidecars are explicit local compatibility for
loopback guards, not a production auth bypass or fabricated provider. M5 evidence
requires a scoped service token file that is refreshed before expiry.
Keep code-first scope: authoring CI/tests does not authorize running tests, builds,
Kustomize/Helm render, Docker, cluster/cloud operations, commit or push in this turn.
Do not delete MaintAI-k3d or modify the app/PDF checkout without a scoped request.

## Publication and source synchronization — 2026-10-29

The user subsequently authorized synchronizing local platform source with the
merged application, pinning ML/RAG bases in the app, and committing/pushing both
platform repositories to public remotes. This supersedes the initial no-commit/
no-push scope for this delivery. Push-triggered source CI is part of publication;
no cloud provisioning, cluster mutation or workload activation was requested.
The local app-source lock and LOCAL_SOURCE_SYNC.md record the reviewed commit.
Do not replace pending model/image/runtime evidence with example values.
