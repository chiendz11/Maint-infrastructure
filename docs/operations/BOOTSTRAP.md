# Future bootstrap order

Initial delivery executed none of these operations. Fill actual environment values
and obtain deployment authorization before using these code paths.

1. Day zero: copy environments/bootstrap.tfvars.example to a private ignored file.
   Reuse an existing account GitHub OIDC provider ARN if it already exists. Bootstrap
   state/KMS/roles with local authorized AWS credentials and its initial local backend, then
   copy terraform/bootstrap/backend.tf.example to backend.tf and migrate that SAME root
   state into encrypted S3 using terraform/backend.hcl.example.
   Never initialize an empty remote state and apply over existing bootstrap resources.
2. Domain: choose an existing hosted zone or create the delegated subdomain zone.
   First apply with wait_for_certificate_validation=false; obtain NS and delegate
   at the parent/registrar. Then apply with true to finish wildcard ACM validation.
   DNS apex is not served; wildcard covers app/simulator subdomains.
3. Platform: supply exact compatible EKS add-on/AMI builds, PostgreSQL and pgvector
   minors, node/CIDR/operator role settings and remote backend configuration.
   Platform reads domain state. RDS/S3/ECR/ledger are protected from destroy.
4. Argo CD: same cluster remote state, AWS exec authentication; keep
   enable_gitops_root=false until GitOps repo/configuration is available. Argo CD
   is private ClusterIP, local admin disabled and needs reviewed SSO configuration
   before interactive use. Kubernetes bootstrap remains owned by Terraform.
5. Handoff: scripts/build_platform_contract.py exports only the allowed v2 output.
   The dedicated platform publisher dispatches GitOps platform-reconcile, which
   opens a PR. Dispatch success is not merge or deployment success.
6. Seed secrets, database owners/migrations and actual workload/model image digests
   via documented GitOps preparation. Review root enablement in infrastructure PR.

Optional future workflows are gated by ENABLE_INFRA_AUTOMATION=true. Apply requires
main, environment prod and exact expected_main_sha, then creates a fresh saved plan
and applies that plan. No automatic destroy workflow exists. Deployment environment
approvals/branch restrictions must be configured in GitHub by an authorized operator.

Required GitHub variables: AWS_REGION, TF_STATE_BUCKET, TF_STATE_KMS_KEY_ARN,
TERRAFORM_PLAN_ROLE_ARN, TERRAFORM_APPLY_ROLE_ARN, TFVARS_BOOTSTRAP_JSON,
TFVARS_DOMAIN_JSON, TFVARS_PLATFORM_JSON, TFVARS_ARGOCD_JSON and publisher App metadata.
Variables hold non-secret metadata only. Passwords/private keys are not TF inputs.

PR plan covers AWS-only roots. Argo CD/Helm plans need live cluster/secret access and
are generated inside the protected apply job, not with the PR-only read role. The
initial dependency cycle (no remote state yet) is a day-zero operator procedure,
not an allegedly successful speculative plan. Static CI is not a Terraform plan.
