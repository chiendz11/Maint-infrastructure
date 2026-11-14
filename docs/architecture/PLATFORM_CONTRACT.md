# Platform contract v2

Terraform producer and GitOps consumer carry identical platform-contract-v2 schema
bytes and SHA locks. Upgrade it through coordinated PRs if semantics change.

Output contains account/region, cluster name/version/VPC ID, private RDS endpoint,
five logical DB names, pinned vector version, admin-secret ARN, four versioned S3
buckets, KMS ARN, approved-dataset queue/ledger, IRSA role ARNs, publisher roles,
ECR allow-list, application secret ARNs and DNS/validated ACM metadata.

No password, private key, provider credential, kubeconfig, Terraform backend state
or full unfiltered terraform output is published. Secret ARNs are references.
Platform renderer does not choose model/image versions or authorize unrelated
application publishers. Stable metadata is canonicalized; a no-change handoff
should not create timestamp-only desired-state diffs.

The default domain phase can return null validated_certificate_arn. Workload edge
activation must wait for the later successful validation phase; never treat an
unvalidated ACM request ARN as ready for traffic.
