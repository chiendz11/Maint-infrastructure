# MaintAI Infrastructure Architecture (`Maint-infrastructure`)

Tài liệu này mô tả kiến trúc **Hạ tầng & Bootstrap (IaC)** do `Maint-infrastructure` quản lý cho cả hai môi trường: **AWS Cloud Production (Terraform/EKS)** và **Local Cluster (`k3d` + LocalStack + Argo CD Bootstrap)**.

---

## 1. Phân Định Ranh Giới Sở Hữu Hạ Tầng vs GitOps

| Thành phần | Owner Repository | Trách nhiệm cụ thể |
| :--- | :--- | :--- |
| **Cloud Infrastructure & Cluster Bootstrap** | **`Maint-infrastructure`** | Terraform AWS (`bootstrap`, `domain`, `platform`, `argocd`), `terraform/local/` (`k3d` cluster), kubeconfig cô lập, LocalStack Secrets Manager, `External Secrets Operator` (ESO), `Ingress-NGINX` (Class `alb`), `cert-manager`, bootstrap Argo CD root & xuất `platform-contract-v2`. |
| **In-Cluster Desired State** | **`MaintAI-gitops`** | Kustomize manifests (`base/`, `environments/{local,production}/`), Argo child Applications, Strimzi Kafka topics/ACLs, PostgreSQL/MinIO/Keycloak local pods, monitoring, ExternalSecrets, HPA/PDB/NetworkPolicies và rollout ứng dụng. |
| **Application Source & Images** | **`MaintAI`** | Codebase microservices, Dockerfiles, contracts v1.4, model bundles, risk policies và CI/CD build/push image lên registry. |

> **Nguyên tắc bất biến:** Không apply cùng một resource Kubernetes từ cả Terraform/CLI của `Maint-infrastructure` lẫn Argo CD của `MaintAI-gitops`. Terraform bootstrap Argo CD (`enable_gitops_root=false` mặc định trên cloud), sau đó bàn giao quyền reconcile in-cluster cho Argo CD.

---

## 2. Kiến Trúc Terraform AWS Production (`terraform/`)

1. **`terraform/bootstrap/`:** Khởi tạo S3 encrypted backend state, KMS key, GitHub OIDC provider và IAM roles phân tách `plan` (ReadOnly) vs `apply`.
2. **`terraform/domain/`:** Route53 hosted zone / delegated subdomain và wildcard ACM certificate (`*.domain` phục vụ Main App và Simulator Edge).
3. **`terraform/platform/`:** VPC/subnets private, NAT, Amazon EKS, Managed Node Groups & IRSA roles, Amazon RDS PostgreSQL 17 (`pgvector`) cho 5 databases tách chủ sở hữu, Amazon S3 versioned buckets, SQS/DLQ (dataset manifest trigger), DynamoDB training lease ledger, ECR repositories và AWS Secrets Manager metadata (chỉ tạo ARN, không đưa giá trị secret vào Terraform variables/state).
4. **`terraform/argocd/`:** Cài đặt Argo CD Helm release (ClusterIP nội bộ, không bật local admin trên cloud) và root Application bootstrap.
5. **Handoff `platform-contract-v2`:** Script `scripts/build_platform_contract.py` xuất các metadata không nhạy cảm (RDS endpoint, bucket names, KMS/IAM ARNs, validated ACM ARN) sang `MaintAI-gitops` qua GitHub dispatch/PR; tuyệt đối không xuất password, kubeconfig hay secret values.

---

## 3. Kiến Trúc Hạ Tầng Local Parity (`terraform/local/` & `local/`)

Thư mục `terraform/local/` và `local/` dựng một cụm `k3d` (`maintai-local`, Kubernetes 1.35) tái tạo sát kiến trúc AWS Production ngay trên máy trạm:

- **Provisioning tách biệt (`90b9f97`):** Terraform chịu trách nhiệm tạo cụm `k3d`, khởi tạo LocalStack (`:4566`), ESO, `Ingress-NGINX`, `cert-manager` và bootstrap Argo CD; phần application provisioning / DB seed được chuyển vào Argo CD PreSync Hooks bên `MaintAI-gitops`.
- **Cloud-Native CoreDNS & TLS (`323e400`):** Mọi connection string cấp từ `localdev` secrets (PostgreSQL, Keycloak, internal services) trỏ trực tiếp tới Kubernetes CoreDNS (`postgres:5432`, v.v.) và sử dụng `cert-manager` thay vì loopback adapter sidecar.
- **Tài sản Private (`local/.local/`):** Chứa private kubeconfig (không ghi đè `~/.kube/config`), CA/TLS keys, credentials, dataset AI4I, local model bundles và image receipts. Toàn bộ được gitignore.
- **CLI Operator (`localdev/`):** Hỗ trợ các tác vụ vận hành tường minh: `init`, `up`, `stop`/`start`, `delete`, `model-identity`, `groq-secret`, `prepare-rag`, `migrate`, `grants`, `provision`, `activate-ordering`, `forward` và `localdev.history` (M6). Chi tiết xem [`local/README.md`](../../local/README.md).
- **Quyết định `UI-01` ở tầng Edge:** Ingress định tuyến độc lập Main Business UI (`app.maintai.local` / `:18080`) tới Business API (`:8003`), và Simulator UI (`simulator.maintai.local` / `:18081`) tới Sensor Control API (`:8005`).

---

## 4. Giới Hạn An Toàn & Tài Liệu Bổ Sung

- **Ranh giới bảo mật chi tiết:** Xem [SECURITY.md](SECURITY.md) (OIDC, IRSA, private subnets, database owner isolation).
- **Hợp đồng bàn giao Cloud:** Xem [PLATFORM_CONTRACT.md](PLATFORM_CONTRACT.md) và [BOOTSTRAP.md](../operations/BOOTSTRAP.md).
- **Quá trình nâng cấp & Demo:** Báo cáo chạy cụm `maintai-local` ngày 30/10 ở [LOCAL_DEMO_RUN_2026-10-30.md](../demos/LOCAL_DEMO_RUN_2026-10-30.md), hướng dẫn M6 History ở [LOCAL_M6_HISTORY.md](../operations/LOCAL_M6_HISTORY.md), và quy trình đồng bộ source lock (`app-source.lock.json`) tại [`MaintAI-gitops/docs/operations/LOCAL_SOURCE_SYNC.md`](../../../MaintAI-gitops/docs/operations/LOCAL_SOURCE_SYNC.md).
- **Giới hạn Local vs Production:** 1-node `k3d`, single-NAT / single-AZ profile mặc định trên AWS demo là cấu hình tiết kiệm chi phí, **không** tự chứng minh AWS High Availability hay capacity 100 máy/giây khi chưa benchmark thực tế.
