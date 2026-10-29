# Versioning and immutable provenance

- Repository version: `VERSION` (initial 0.1.0).
- App baseline: 1.3.1; platform decision: `maintai-1.3.1+simulator-ui.1`.
- Platform handoff: schema **2.0.0** (five DBs, new workloads/roles/storage).
- Workload/model/dataset/recovery intents: their own 1.0.0 schemas.
- Runtime config schemas: **2.0.0**, immutable by filename and SHA-256; producer
  must declare the exact approved schema hash for every runtime in an image group.
- Event versions are independent; do not replace the unresolved inference.results
  version with the architecture/repository version.
- App image: exact ECR `repository@sha256`, source Git SHA, owner/signature workflow.
  Shared Processing/Business images update their runtime group atomically.
- Platform chart/provider versions are exact pins, never latest/most_recent.
  EKS regional add-on builds, AMI and PostgreSQL minor are explicit required inputs.
- Operator-managed broker/controller images follow the pinned controller/chart
  release; operator/chart compatibility still needs a later deployment review.
- Dataset/protocol/model/preprocessor/reference/metadata/evaluation report objects
  retain bucket, key, **S3 VersionId + SHA-256**. ETag is not a substitute.
- Model threshold is chosen on validation; test split/protocol has immutable hash.
- Do not mutate a published model object/config schema in place. A new model bundle,
  schema filename/version or config digest goes through a new PR.
- Terraform state uses encrypted versioned S3 + native lockfiles. Initial provider
  checksum locks were carried from the local earlier blueprint with matching pins;
  no provider install or dependency resolution was executed in this task.

Reference commits and supplied document hashes are recorded in docs/. Application
source is currently uncommitted, so its document content hashes are used rather
than falsely claiming those documents are in the app's HEAD commit.

A dispatch ACK != a created PR != a merged PR != Argo convergence != serving a
validated model. Keep each stage's evidence separate. Reverting a GitOps commit
cannot undo database migrations, erase published messages, or restore lost data.

## PROC-ORDER-01 source/metadata amendment — 2026-10-23

Current application design is1.4.0 plus decision PROC-ORDER-01/1.0.0. Platform
baseline1.3.1/architecture revision and existing contract2.0.0 stay independently
versioned. SDK0.2.0/bundle1.1.0 add Processing migration002; frozen001 and wire
versions/topics are unchanged. Imported source locks remain historical evidence;
active-doc hashes are recorded separately, without claiming an uncommitted app
working tree is already available at a release SHA.

GitOps holds opt-in config3.0.0 Worker/Relay schemas and NOT_ACTIVATED profile.
Frozen2.0.0 bytes and active state remain unchanged. Receiver/publisher/config3
cutover, callback/image/source SHA, owner migration/activation and runtime health
reviews precede enablement. Do not update old schema hashes to hide incompatible
keys, auto-reset inbox/outbox, or equate PR dispatch with deployment success.

## Local environment amendment — 2026-10-29

The separate MaintAI-k3d source is a migration reference, not the new active
ownership boundary. Local infrastructure/Argo bootstrap lives in Maint-infrastructure;
local Kubernetes desired state lives in MaintAI-gitops/environments/local.
The local handoff uses actual M5 entrypoints and SDK0.3/bundle2/outcome1.4,
separate from dated production1.3.1/config2.0 snapshots above. No production
activation, wire/schema change, build, test, deployment or benchmark is implied.
