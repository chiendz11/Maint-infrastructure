# Platform Metadata Handoff (SSM Parameter Store & Terraform Outputs)

Thay cho cơ chế `platform-contract-v2` webhook dispatch trước đây (`scripts/dispatch_platform.py` -> `platform-reconcile.yml`), luồng bàn giao hạ tầng Production sử dụng mô hình **Pull-Based AWS Native + Pure Declarative GitOps**:

1. **Nguồn dữ liệu Production (`terraform/platform/outputs.tf`):**
   - Resource `aws_ssm_parameter.platform_metadata` (`/maintai/v13/production/platform-metadata`, `type = "String"`, `tier = "Advanced"`) và Terraform output `platform_metadata` (alias tương thích `platform_contract`) lưu các metadata **không nhạy cảm**:
     - `aws` (`account_id`, `region`), `cluster` (`name`, `version`, `vpc_id`)
     - `database` (`host`, `port = 5432`, 5 logical DBs, pinned `pgvector_version`, `master_secret_arn`)
     - `storage` (4 versioned S3 buckets), `kms_key_arn`
     - `training` (`queue_name`, `queue_arn`, `ledger_table`)
     - `roles` (toàn bộ IRSA Role ARNs, bao gồm `external-secrets` và `image-updater` cho `argocd:argocd-image-updater-controller`)
     - `publishers` (`app`, `reader`, `dataset`)
     - `images` (15 ECR repository URLs khớp 1-1 với `MaintAI` runtime & MLOps components)
     - `secrets` (Secrets Manager ARNs — chỉ tham chiếu ARN, kể cả `argocd-image-updater-git-creds`, tuyệt đối không chứa secret value)
     - `ingress` (`domain`, `hosted_zone_id`, `certificate_arn`)

2. **Nguyên tắc an toàn bất biến:**
   - Tuyệt đối không xuất password, private key, GitHub PAT, kubeconfig hoặc Terraform backend state vào SSM parameter hoặc Git.
   - `Maint-infrastructure` không push/dispatch trực tiếp vào `MaintAI-gitops`; mọi cập nhật trong GitOps đi qua Pull Request có CI kiểm tra (`kubectl kustomize` + `kubeconform`).
   - Phase mặc định của `domain` có thể trả `validated_certificate_arn = null`; chỉ kích hoạt Workload Edge sau khi DNS delegation và ACM validation hoàn tất.
