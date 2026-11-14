# Maint-infrastructure Documentation Index

Tài liệu quản lý Hạ tầng Cloud (`AWS Terraform`) và cụm **Local `k3d` + Argo CD bootstrap** cho hệ thống MaintAI.

## Cấu trúc thư mục

| Thư mục | Phạm vi |
| :--- | :--- |
| [`architecture/`](architecture/) | Kiến trúc hạ tầng AWS/Local, Platform Contract v2, ranh giới bảo mật & quy tắc versioning/provenance. |
| [`operations/`](operations/) | Hướng dẫn bootstrap AWS/Argo CD và thiết lập M6 History (`KMS/RSA keys`, `ESO`, `grants`). |
| [`demos/`](demos/) | Báo cáo chạy thử thực tế (`maintai-local`) và 3 kịch bản video/scale/model-rollout. |

---

## Danh mục tài liệu

### Architecture & Governance
- [ARCHITECTURE.md](architecture/ARCHITECTURE.md) — Stack Terraform Production (`bootstrap`, `domain`, `platform`, `argocd`) & Local `k3d` (`CoreDNS`, `90b9f97`).
- [PLATFORM_CONTRACT.md](architecture/PLATFORM_CONTRACT.md) — Hợp đồng bàn giao hạ tầng `platform-contract-v2` sang `MaintAI-gitops`.
- [SECURITY.md](architecture/SECURITY.md) — Ranh giới bảo mật, OIDC, IRSA, private subnets, PostgreSQL owner isolation & secrets.
- [VERSIONING.md](architecture/VERSIONING.md) — Khóa provider/AWS pins, `local/versions/app-source.lock.json` (`e67d42d`), Iris blueprint provenance.

### Operations
- [BOOTSTRAP.md](operations/BOOTSTRAP.md) — Thứ tự khởi tạo Terraform bootstrap/domain/platform/argocd và manual DB migrations.
- [LOCAL_M6_HISTORY.md](operations/LOCAL_M6_HISTORY.md) — Quy trình bật History M6 (RSA delegation/cursor keys, LocalStack/ESO, grants).

### Demos & Run Reports
- [LOCAL_DEMO_RUN_2026-10-30.md](demos/LOCAL_DEMO_RUN_2026-10-30.md) — Báo cáo thực thi cụm `maintai-local` (kèm phần cấu hình GitOps đã áp dụng & ghi chú cập nhật `main`).
- [LOCAL_DEMO_VIDEO_SCRIPT.md](demos/LOCAL_DEMO_VIDEO_SCRIPT.md) — Kịch bản và lời thoại video demo chính (13–15 phút).
- [LOCAL_SCALE_DEMO_SCRIPT.md](demos/LOCAL_SCALE_DEMO_SCRIPT.md) — Kịch bản & lời thoại demo scale HTTP/HPA và Processing/Kafka.
- [LOCAL_MODEL_ROLLOUT_VIDEO_SCRIPT.md](demos/LOCAL_MODEL_ROLLOUT_VIDEO_SCRIPT.md) — Kịch bản train HGB, MLflow registry & shadow rollout (`ml-service-shadow`).

> **Tài liệu vận hành CLI `localdev` & quy trình sync GitOps:** Xem [local/README.md](../local/README.md) và [`MaintAI-gitops/docs/README.md`](../../MaintAI-gitops/docs/README.md).
