# Versioning and Infrastructure Provenance (`Maint-infrastructure`)

Tài liệu này quy định việc khóa phiên bản cho Terraform providers, tài nguyên hạ tầng AWS, và kiểm chứng nguồn ứng dụng (`MaintAI`) tại `Maint-infrastructure`.

---

## 1. AWS Infrastructure & Terraform Provenance

- **Repository version:** `VERSION` (initial `0.1.0`).
- **Platform baseline & App target:** Platform baseline `maintai-1.3.1+simulator-ui.1`; application contracts target `1.4.0` (`PROC-ORDER-01/1.0.0`).
- **Terraform Provider Locks:** Toàn bộ providers (`aws`, `helm`, `null`, `local`, v.v.) sử dụng exact pin và lockfiles; state Production dùng S3 encrypted + versioning + native state lock.
- **AWS Resource Pins:** EKS cluster/add-on builds, AMI release và RDS PostgreSQL + `pgvector` minor version phải được khai báo tường minh theo từng region — tuyệt đối không dùng `latest` hoặc `most_recent`.
- **Platform Contract Handshake:** `contracts/platform-contract-v2.schema.json` được khóa bằng `versions/contracts.lock.json`; bản sao schema giữa `Maint-infrastructure` và `MaintAI-gitops` phải khớp từng byte.
- **S3 Artifacts:** Mọi dataset/model/reference objects dùng chung trên AWS đều khóa bằng `S3 VersionId + SHA-256` (ETag không thay thế checksum).

---

## 2. Local Infrastructure Locks & Reference Provenance

- **App Source Lock (`local/versions/app-source.lock.json`):** Khóa chính xác Git commit của `chiendz11/MaintAI` (hiện đồng bộ tại **`e67d42d0d2fd347c686a39928906c20b68f03992`**, nhánh `main`) và SHA-256 của toàn bộ Dockerfiles, settings và kafka/risk-policy interfaces. CI (`ci.yml`) checkout trực tiếp `.ci-app` ở commit này và kiểm tra hash từng file qua `python -m localdev.checks --app-root .ci-app`.
- **Platform & Local Contract Locks:**
  - `local/versions/platform.lock.json`: Khóa digest images nền tảng local (MinIO/MC source tar hashes, dev-tools, Argo CD installer SHA-256, k3d v5.9.0 / kubectl pins).
  - `versions/local-contracts.lock.json`: Bảo vệ schema local `1.0.0` (`image-receipt`, `local-profile`).
  - `versions/local-production-baseline.lock.json`: Bảo vệ toàn vẹn các file Terraform AWS production khỏi chỉnh sửa ngoài ý muốn khi cập nhật phần local.
- **App-Owned Risk Policy (`RISK-POLICY-01`):** `Maint-infrastructure` chỉ kiểm `app-source.lock.json` và chuyển `--app-root` sang GitOps; không giữ bản policy chỉnh tay trong `local/.local/data/fixtures/`. Chi tiết xem [`MaintAI-gitops/docs/operations/LOCAL_SOURCE_SYNC.md`](../../../MaintAI-gitops/docs/operations/LOCAL_SOURCE_SYNC.md).
- **Iris Blueprint Provenance:** Mẫu tách repo Terraform/GitOps tham chiếu ban đầu từ `chiendz11/iris-gitops` (`ed951731ce378a6468bf01e4bb80376b8e39872a`) và `chiendz11/iris-infrastructure` (`6c661a6eee543ac23dd9d998ceef59b3e3804929`, ngày 18/10/2026); không copy secrets, state hay KServe protocol.
