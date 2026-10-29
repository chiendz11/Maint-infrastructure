
## Public source synchronization — 2026-10-29

App lock now references committed SHA `7c05489f705e0f55c45d03252869e27760da1c25` (PR15/16/19 and Storage0.2.1).
Both platform CI workflows verify the exact app revision and selected file hashes.
Schema1.0.0, production fingerprints and disabled release gates remain unchanged.
See [source sync](LOCAL_SOURCE_SYNC.md) for public remotes and runtime inputs.

## RISK-POLICY-01 — 30/10/2026

App policy JSON/schema/catalog là source chuẩn. Selector GitOps khóa app SHA,
version, raw SHA và canonical policy SHA; Kustomize ConfigMap content hash làm
rollout Worker. App source locks hai repo cùng khóa policy source. Local profile
schema1.0.0 và production fingerprints giữ nguyên. Model identity vẫn riêng.
Xem [policy runbook](LOCAL_RISK_POLICY.md).
