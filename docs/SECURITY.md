# Security boundaries and operational prerequisites

Cloud CI uses GitHub OIDC, not long-lived AWS access keys. Subjects bind exact
repository and PR/prod environment. Fork PRs cannot run the plan job. The plan
role uses ReadOnlyAccess plus state read/native-lock writes. The bootstrap apply
role is intentionally an initial privileged provisioning role; review a permissions
boundary and project-specific least privilege before multi-user operation.

AWS resources are private where applicable: nodes/RDS on private subnets, RDS TLS
required, EKS endpoint access constrained by explicit operator/runner CIDRs. DB
security group allows EKS node group traffic. Kubernetes network policy and
owner-specific credentials further constrain service access; database owner roles
are created outside Terraform by an explicit operation.

IRSA trust binds exact service account+namespace. Training cannot approve datasets;
S3 raw does not trigger training. App publisher ECR access is separate from platform
publisher, dataset publisher, model dispatch and runtime credentials. Ingestion has
no DB credential. External Secrets can read only explicit secret ARNs and KMS key.

Secret values are never Terraform resources/variables. No actual environment tfvars,
keys or state were copied from Iris or earlier MaintAI folders. Provider locks were
reused as versioned source, not installed/validated during this task.

Single NAT/single-AZ RDS default is a demo profile. Review HA, backups/restores,
retention, resource sizing and management ingress before deployment. These are
explicit properties of this draft, not tested production guarantees.
