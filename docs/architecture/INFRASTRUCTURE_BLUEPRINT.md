# Cloud & Local-Parity Infrastructure Blueprint (Terraform + EKS/k3d + Argo CD Bootstrap)

Tài liệu mẫu chuẩn (project-agnostic) để tái sử dụng kiến trúc **Infrastructure-as-Code (IaC)** cho bất kỳ hệ thống microservices/AI nào chạy trên Kubernetes, đảm bảo **tương đồng kiến trúc giữa Local (`k3d` + LocalStack) và Production (`AWS EKS`)** mà vẫn giữ ranh giới bảo mật sạch với GitOps.

> Được đúc kết từ kiến trúc thực tế của `Maint-infrastructure`. Chỉ cần thay thế các placeholder `<project>`, `<org>`, `<region>`, `<domain>`, `<aws-account-id>` là có thể áp dụng cho dự án mới.

---

## 1. Ranh giới trách nhiệm của `<project>-infra`

Trong mô hình 3 repository (`<project>-app`, `<project>-infra`, `<project>-gitops`), `<project>-infra` chịu trách nhiệm duy nhất về **nền tảng hạ tầng và bootstrap cluster**:

- **Quản lý bởi `<project>-infra`**:
  - Cloud networking & compute: VPC, Subnets (Public/Private), NAT Gateway, Security Groups, EKS Cluster, Managed Node Groups / Karpenter.
  - Managed stateful services: RDS/Aurora, S3 buckets, KMS keys, SQS/SNS/DynamoDB, ECR repositories.
  - Danh tính & phân quyền: GitHub OIDC providers, AWS IAM Roles (IRSA / EKS Pod Identity), DNS/TLS (`Route53` + `ACM`).
  - Cluster bootstrap tối thiểu: Argo CD Helm release, Root `Application` pointer sang `<project>-gitops`, hoặc cụm Local `k3d` + LocalStack mô phỏng AWS.
- **KHÔNG quản lý trong `<project>-infra`**:
  - Code ứng dụng và quy trình build image (`<project>-app`).
  - Manifests chi tiết của từng microservice, dashboard Grafana, hay danh sách `images:` override (`<project>-gitops`).
  - Giá trị secret plaintext (`DB password`, `PAT`, `API keys`, `TLS private key`) bên trong Terraform `.tf` hoặc `terraform.tfstate`.

---

## 2. Kiến trúc Terraform phân tầng (Layered Root Modules)

Chia Terraform thành **4 state roots độc lập** theo chu kỳ thay đổi (*blast radius*) để giảm rủi ro khi `apply` và cho phép phân quyền CI riêng cho từng tầng:

```text
1. terraform/bootstrap/   ──(Remote State S3 + KMS + GitHub OIDC + CI Roles)
         │
         ▼
2. terraform/domain/      ──(Route53 Hosted Zone + ACM TLS Certificates)
         │
         ▼
3. terraform/platform/    ──(VPC, EKS, RDS, S3, ECR, KMS, IRSA cho Workloads & Addons)
         │
         ▼
4. terraform/argocd/      ──(Helm Argo CD + Image Updater IRSA/Creds + Root App Bootstrap)
         │
         ▼
   [<project>-gitops]     ──(Tự tiếp quản Platform Addons + Observability + Apps)
```

### Quy ước thư mục chuẩn cho `<project>-infra`

```text
<project>-infra/
├── .github/
│   └── workflows/
│       ├── ci.yml                  # Policy lint (no secrets/most_recent), unit tests
│       ├── terraform-plan.yml      # Plan cả 4 roots trên PR (OIDC read/plan role)
│       └── apply.yml               # Workflow dispatch theo từng root với Environment gate
├── terraform/
│   ├── bootstrap/                  # S3 backend, DynamoDB/S3 lockfile, GitHub OIDC
│   ├── domain/                     # Route53 + ACM
│   ├── platform/                   # VPC, EKS, RDS, ECR, S3, KMS, IRSA
│   └── argocd/                     # Argo CD Helm + Root GitOps bootstrap
├── environments/
│   ├── dev.tfvars.example
│   └── prod.tfvars.example
├── scripts/
│   └── source_policy.py            # Static guardrails cho Terraform & versions lock
├── local/                          # (Tùy chọn) Wrapper dựng cụm Local k3d + LocalStack
│   ├── manifests/                  # ClusterSecretStore mẫu, cert-manager issuer local
│   ├── localdev/                   # CLI Python: up / down / status / pat / verify
│   └── tests/                      # Unit tests không cần cluster
└── docs/
    └── README.md
```

> **Gợi ý tách bạch khi scale team**: Nếu team lớn, hãy giữ `local/` thuần gọn hoặc tách thành module CLI phụ thuộc ít nhất có thể vào biến nội bộ, tránh để cấu hình test local làm nhiễu pipeline Production Terraform.

---

## 3. Quy tắc Bảo mật & Guardrails (Static Policy Checks)

### 3.1. Tuyệt đối không đưa Secret vào Terraform State
- **Cấm `aws_secretsmanager_secret_version`** trong `.tf`: Terraform chỉ tạo vỏ `aws_secretsmanager_secret` (metadata + KMS key + rotation policy), còn giá trị thực (`SecretString`) được nạp ngoài luồng (out-of-band CLI/vault admin) hoặc qua runtime bootstrap.
- **Cấm `most_recent = true` / mutable version pins**: Mọi AMI, Helm chart version, Terraform provider và module version phải ghim cố định (*exact pin*) để đảm bảo `terraform plan` tái lập (*reproducible*).

Ví dụ script guardrail `scripts/source_policy.py` chạy bắt buộc trong CI:

```python
from pathlib import Path
import re
import sys

FORBIDDEN_PATTERNS = {
    r"\bmost_recent\s*=\s*true\b": "Pinned AMI/data version is required; forbid most_recent = true",
    r'resource\s+"aws_secretsmanager_secret_version"': "Forbid storing secret values in Terraform state",
}

errors = []
for tf_file in Path("terraform").rglob("*.tf"):
    content = tf_file.read_text(encoding="utf-8")
    for pattern, reason in FORBIDDEN_PATTERNS.items():
        if re.search(pattern, content):
            errors.append(f"{tf_file}: {reason}")

if errors:
    print("\n".join(errors), file=sys.stderr)
    sys.exit(1)
print("Terraform security policy checks passed.")
```

### 3.2. Zero Static AWS Keys trên CI (GitHub OIDC)
- Tạo 2 nhóm IAM Role qua GitHub OIDC (`token.actions.githubusercontent.com`):
  1. **Infra Plan Role** (`pull_request`): Chỉ có quyền `ReadOnly` + `s3:GetObject` trên state để chạy `terraform plan` (không có quyền `Put`/`Apply`).
  2. **Infra Apply Role** (`main` + GitHub Environment `prod` có Manual Approval): Có quyền apply vào tầng tương ứng.
  3. **App ECR Publisher Role** (chỉ trust `<org>/<project>-app`, branch `main` hoặc tag `v*.*.*`): Chỉ có quyền push vào đúng danh sách ECR repositories của ứng dụng.

### 3.3. Least-Privilege IRSA cho EKS & Argo CD Image Updater
- Mọi ServiceAccount cần truy cập AWS đều dùng **IRSA** (hoặc EKS Pod Identity) gắn chặt theo cặp `<namespace>:<service-account-name>`:
  - `external-secrets:external-secrets`: chỉ đọc `secretsmanager:GetSecretValue` với prefix `<project>/<env>/*`.
  - `argocd:argocd-image-updater-controller`: nếu Production dùng Amazon ECR private, cấp tối thiểu quyền đọc registry (`ecr:GetAuthorizationToken`, `ecr:BatchCheckLayerAvailability`, `ecr:GetDownloadUrlForLayer`, `ecr:DescribeImages`, `ecr:ListImages`) cho `argocd-image-updater`.
  - `<app-ns>:<service-sa>`: chỉ đọc/ghi đúng S3 prefix, SQS queue hoặc KMS key mà service đó sở hữu.

---

## 4. Thiết kế tầng `terraform/argocd/` cho Production GitOps

Trong kiến trúc Pure Declarative GitOps, tầng `terraform/argocd/` đóng vai trò cầu nối bàn giao hạ tầng sang `<project>-gitops`:

1. **Cài đặt `argo-cd` Helm chart** (pinned version) vào namespace `argocd`.
2. **Chuẩn bị quyền đọc Container Registry cho Image Updater**:
   - Tạo IAM Role (IRSA) gắn annotation `eks.amazonaws.com/role-arn` cho ServiceAccount `argocd-image-updater-controller` (nếu dùng ECR) hoặc đồng bộ GHCR pull secret từ Secrets Manager.
3. **Chuẩn bị quyền mở PR sang `<project>-gitops`**:
   - Nạp Secret `argocd/argocd-image-updater-git-creds` chứa Fine-grained PAT hoặc GitHub App key thông qua AWS Secrets Manager + ESO (khuyến nghị) hoặc nạp out-of-band trước khi bật `enable_gitops_root = true`.
4. **Bàn giao Infra Outputs sang GitOps mà không chạy script dispatch ad-hoc**:
   - **Cách sạch nhất**: `terraform/platform` ghi các endpoint/ARN cần thiết (RDS host, S3 bucket, KMS ARN, Role ARN) vào **AWS SSM Parameter Store** hoặc **AWS Secrets Manager**, để `<project>-gitops` tự đọc bằng `ExternalSecret` — hoàn toàn không cần `Maint-infrastructure` CI tạo commit hay gọi webhook sang repo GitOps.
   - Nếu cần đưa giá trị tĩnh vào `ConfigMap` (không nhạy cảm), dùng `terraform output -json` đẩy qua PR chuẩn hoặc dùng ESO Sync cho cả cấu hình không mật.
5. **Kích hoạt Root Application**: Deploy chart/manifest trỏ về `bootstrap/production` của `<project>-gitops`.

---

## 5. Mô hình Local Cloud-Parity (`k3d` + LocalStack + ESO)

Để môi trường phát triển Local kiểm chứng được **đúng hành vi Production** (Ingress TLS, External Secrets, Image Updater PR loop, ServiceAccount RBAC) mà không tốn chi phí cloud:

| Thành phần Production (AWS) | Thành phần Local-Parity (`k3d`) | Ghi chú tương đồng |
| :--- | :--- | :--- |
| **Amazon EKS** | **`k3d` (k3s in Docker)** | Cấp cluster K8s chuẩn, CoreDNS rewrite domain local nếu cần |
| **AWS Secrets Manager + KMS** | **LocalStack (`secretsmanager`, `s3`)** | Giữ nguyên CRD `ClusterSecretStore` + `ExternalSecret` ở `<project>-gitops` |
| **Route53 + ACM** | **Ingress-NGINX + `cert-manager` (`selfSigned` / Local CA)** | Giữ nguyên TLS termination qua Ingress |
| **ECR Publisher + Pull** | **GHCR + Image tag `sha-<40>`** | Image Updater vẫn poll registry và mở PR thật về GitOps |
| **IRSA AWS Auth** | **Bootstrap Secret cho ESO (`aws-secrets-manager` + `aws-secrets-manager-argocd`)** | `localdev image-updater-pat` nạp `maintai/local/gitops` vào LocalStack qua stdin; ESO đồng bộ thành `argocd/argocd-image-updater-git-creds` (giống 100% flow AWS Secrets Manager Production) |

### Nguyên tắc bảo mật cho Local Bootstrap CLI
- **Không lưu PAT hay API key vào file `.env` commit lên Git hay tham số dòng lệnh** (tránh lộ trong `ps aux` và shell history): luôn đọc qua stdin/biến môi trường tạm (`getpass`) rồi `kubectl apply -f -` trực tiếp vào cluster.
- **Cô lập `kubeconfig`**: ghi kubeconfig vào thư mục riêng với quyền `chmod 0600`, không ghi đè `~/.kube/config` mặc định của người dùng.
- **Phạm vi `ClusterSecretStore`**: giới hạn namespace bằng `conditions` (`namespaces: [<project>-local]`) để tránh workload ngoài đọc nhầm secret.

---

## 6. Mẫu CI/CD chuẩn cho `<project>-infra`

### 6.1. Validation & Plan trên Pull Request (`.github/workflows/terraform-plan.yml`)

Luôn chạy **`terraform fmt -check`**, **`terraform validate`**, **`source_policy.py`**, và **`terraform plan`** cho **tất cả các root modules (`bootstrap`, `domain`, `platform`, `argocd`)**:

```yaml
name: Terraform Plan
on:
  pull_request:
    paths:
      - "terraform/**"
      - "environments/**"
      - "scripts/**"

permissions:
  id-token: write
  contents: read
  pull-requests: write

jobs:
  plan:
    strategy:
      fail-fast: false
      matrix:
        root: [bootstrap, domain, platform, argocd]
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.9.8"
      - run: python3 scripts/source_policy.py
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_PLAN_ROLE_ARN }}
          aws-region: ${{ vars.AWS_REGION }}
      - working-directory: terraform/${{ matrix.root }}
        run: |
          terraform fmt -check -recursive
          terraform init -input=false
          terraform validate
          terraform plan -no-color -input=false -var-file=../../environments/prod.tfvars
```

### 6.2. Controlled Apply (`workflow_dispatch` + GitHub Environment Gate)

Không tự động `terraform apply` khi merge để tránh rủi ro phá hủy stateful resources (RDS/EKS). Chỉ chạy qua `workflow_dispatch` trên `main` và gắn `environment: prod` yêu cầu reviewer phê duyệt trước khi chạy:

```yaml
name: Terraform Apply
on:
  workflow_dispatch:
    inputs:
      root:
        type: choice
        required: true
        options: [bootstrap, domain, platform, argocd]

permissions:
  id-token: write
  contents: read

jobs:
  apply:
    runs-on: ubuntu-24.04
    environment: prod
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.9.8"
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_APPLY_ROLE_ARN }}
          aws-region: ${{ vars.AWS_REGION }}
      - working-directory: terraform/${{ inputs.root }}
        run: |
          terraform init -input=false
          terraform apply -auto-approve -input=false -var-file=../../environments/prod.tfvars
```

---

## 7. Checklist áp dụng cho dự án mới

- [ ] Khởi tạo `terraform/bootstrap/` (S3 state encrypted + GitHub OIDC) trước tiên.
- [ ] Thiết lập `scripts/source_policy.py` trong CI để chặn `most_recent = true`, secret trong TF state và kiểm tra pin version provider/module.
- [ ] Khai báo đủ 4 roots (`bootstrap`, `domain`, `platform`, `argocd`) trong `terraform-plan.yml` để không bỏ sót thay đổi ở `argocd`.
- [ ] Cấp IRSA least-privilege cho `external-secrets` và `argocd-image-updater-controller` (nếu dùng private ECR) trong `terraform/platform/`.
- [ ] Dùng Secrets Manager / SSM Parameter Store làm điểm bàn giao dữ liệu sang `<project>-gitops` qua `ExternalSecret` (loại bỏ các script `repository_dispatch` ghi đè GitOps).
- [ ] Bật GitHub Environment `prod` với Required Reviewers cho workflow `apply.yml`.
- [ ] Nếu hỗ trợ Local `k3d`: tách gọn mã nguồn CLI local, không trộn state/lock của local vào lifecycle của Production Terraform.
