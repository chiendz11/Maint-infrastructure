# Bàn giao local k3d + Argo CD + GitOps

## 1. Kết quả và phạm vi

Đã bổ sung local development trực tiếp vào hai repo, dùng ZIP làm tham khảo và
đối chiếu app M5 ở commit45f46ef. Infrastructure bootstrap cluster/private
kubeconfig/secrets/Argo; GitOps quản lý desired state platform/monitoring/apps.
AWS/production resources/config/contracts cũ giữ nguyên bytes trong lượt này.
Không sửa app checkout/PDF và không xóa/chạy folder MaintAI-k3d.

Source/config/CI/tests đã được viết. Chỉ đọc/so sánh source, parse cú pháp
Python/JSON/YAML và ghi nhận upstream pin metadata qua HTTP read-only. Chưa chạy
unit tests, project validators, Kustomize/Helm render, builds, Docker, k3d,
Argo sync, Terraform, GitHub Actions hoặc E2E. Các repo vẫn chưa commit/push.

## 2. Các quyết định và lý do

- Private kubeconfig và ownership marker giúp tooling local không thay current
  context hoặc vô tình nhận quyền quản lý cluster cũ cùng tên.
- Three Argo Applications tách platform/observability/apps để nhìn rõ readiness;
  app defaults disabled, không tạo ACK/inference/model/Alert giả.
- Sync waves tạo Namespace/ConfigMaps trước Services và Pods, rồi mới chạy
  bootstrap Jobs; tránh vòng chờ readiness khi realm config chưa được tạo.
- Native Keycloak dev + local TLS/PKCE và client credentials giải quyết auth;
  adapters chỉ nối loopback profiles, không sửa app/shared security guards.
- M5 API/Consumer nhận scoped Processing token qua file refresh trước expiry;
  Worker registry token chỉ có read role/machine scope, không có mutation quyền.
- Actual image-ID aliases + Git/dirty/snapshot/Dockerfile receipts thay :dev;
  Kustomize config hashes thay đổi cùng config để rollout có căn cứ.
- Correct owner CLI migrations/grants/provision/activation là explicit Jobs, không
  SQL startup hoặc Terraform. Evidence/offset/source ordering không bị reset.
- Kafka12 partitions/four topics, PostgreSQL17/five DB owners, seven versioned
  buckets/scoped credentials giữ các boundary đã chốt. Smoke dùng topic riêng.
- Business/Simulator UI là hai images/Deployments và hai edge routes; Grafana và
  MLflow dùng native UI. MLflow chỉ bật sau app image/base compatibility review.
- Local training là approved manual Job, ghi immutable dataset manifest locator;
  không tự retrain/promote theo sensor/drift. Runtime/quality gates thuộc ML owner.
- Production/file/schema fingerprints và CI roots tách local/production để không
  dùng local setup làm evidence production hoặc âm thầm đổi frozen contracts.

## 3. Giới hạn và công việc khi chạy thật

Cần commit source, build/import actual images, push GitOps remote thật, trust CA
trong browser, sync platform, owner migrations/grants/registry/ordering rồi mới
prepare app release. ML/RAG/training Dockerfiles hoặc model chưa sẵn sàng phải do
owner hoàn thiện; Drift provider/base pins và MLflow base/server/SDK review cũng
chưa được giả thành xong. Kafka exporter chưa có; Grafana lag panel có thể No data.

Single-node local/PVC/Argo health không chứng minh AWS HA, model quality, complete
pipeline hoặc latency100 máy. Cần chạy các tầng verification riêng khi được yêu
cầu; recorded operator attestations không phải kết quả test/benchmark.

## 4. Danh sách file trong Maint-infrastructure

So với source snapshot trước lượt này: **33 file mới, 5 file sửa**, không xóa file hiện hữu. Repo chưa có commit nên đây là so sánh filesystem hash, không giả định có Git diff từ một release.

| File | Thay đổi | Mục đích |
| --- | --- | --- |
| [.github/workflows/ci.yml](../.github/workflows/ci.yml) | Sửa | Bổ sung locked local dependencies, source/contract/gate tests; GitOps render local và production bằng checksum-pinned kubectl. CI required giữ nguyên tên. |
| [AGENTS.md](../AGENTS.md) | Sửa | Cập nhật phạm vi hai repo, ownership local mới, M5/token invariants và giới hạn code-first. |
| [Makefile](../Makefile) | Mới | Shortcuts explicit local commands; không tự chạy khi mở repo. |
| [README.md](../README.md) | Sửa | Thêm điểm bắt đầu local dev; giữ rõ AWS/production baseline độc lập. |
| [contracts/local/image-receipt-v1.schema.json](../contracts/local/image-receipt-v1.schema.json) | Mới | Schema local1.0.0 cho reviewed profiles hoặc actual image receipts; không sửa published production schemas. |
| [contracts/local/local-profile-v1.schema.json](../contracts/local/local-profile-v1.schema.json) | Mới | Schema local1.0.0 cho reviewed profiles hoặc actual image receipts; không sửa published production schemas. |
| [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) | Sửa | Ghi amendment local: cluster/bootstrap ở infrastructure, in-cluster desired state ở GitOps; dated production baseline không tự thành runtime evidence. |
| [docs/LOCAL_DEVELOPMENT.md](../docs/LOCAL_DEVELOPMENT.md) | Mới | Hướng dẫn ownership, release, auth M5, schema/profile, dữ liệu, UI và nghiệm thu local; hoặc entrypoint tới runbook infrastructure. |
| [docs/LOCAL_IMPLEMENTATION_REPORT.md](../docs/LOCAL_IMPLEMENTATION_REPORT.md) | Mới | Báo cáo bàn giao này: chức năng, lý do, danh sách đủ file và giới hạn verification. |
| [docs/VERSIONING.md](../docs/VERSIONING.md) | Sửa | Ghi independent local handoff/versioning và bảo toàn frozen production state. |
| [local/.gitignore](../local/.gitignore) | Mới | Loại private state/data khỏi Git. |
| [local/README.md](../local/README.md) | Mới | Runbook operator đầy đủ: yêu cầu, bootstrap, auth/TLS, image receipts, owner jobs, profile/Git release, URLs, training và giới hạn. |
| [local/VERSION](../local/VERSION) | Mới | Phiên bản phần local1.0.0, độc lập app/Kafka/production contract versions. |
| [local/config/buckets.json](../local/config/buckets.json) | Mới | Bảy versioned buckets và read/write scope cho từng bên sử dụng. |
| [local/config/contract.json](../local/config/contract.json) | Mới | Handoff namespace/context/issuer/ports/Argo paths/Kafka baseline giữa hai repo. |
| [local/config/k3d.yaml](../local/config/k3d.yaml) | Mới | Pinned k3d one-server config, private API, host mounts và loopback NodePort mappings. |
| [local/config/runtime-catalog.json](../local/config/runtime-catalog.json) | Mới | Actual Dockerfile/context/entrypoint/ports/migration catalog, không suy từ placeholder metadata cũ. |
| [local/config/settings.example.json](../local/config/settings.example.json) | Mới | Mẫu non-secret settings: repo/revision/path/machine count; URL thật phải do operator điền. |
| [local/images/mc.Dockerfile](../local/images/mc.Dockerfile) | Mới | Source-built MinIO/mc Dockerfile với tar SHA256 và builder/runtime OCI digests. |
| [local/images/minio.Dockerfile](../local/images/minio.Dockerfile) | Mới | Source-built MinIO/mc Dockerfile với tar SHA256 và builder/runtime OCI digests. |
| [local/install_ci_kubectl.py](../local/install_ci_kubectl.py) | Mới | Tải kubectl CI bằng official version + SHA256, không có kubeconfig/cluster command. |
| [local/requirements.lock](../local/requirements.lock) | Mới | Dependency lock cho local operator/CI, không thêm thư viện vào ứng dụng. |
| [local/runtime/Dockerfile](../local/runtime/Dockerfile) | Mới | Image dev-tools từ Python base digest; non-root, không chứa source app, ML giả hoặc credentials. |
| [local/runtime/bridge.py](../local/runtime/bridge.py) | Mới | HTTP/TCP/TLS adapters giới hạn concurrency; inject bearer chỉ ở loopback routes, giữ caller auth và không retry POST. |
| [local/runtime/main.py](../local/runtime/main.py) | Mới | Entrypoint serve/tokens-once/verify-files, shutdown và checksum artifact lock. |
| [local/runtime/oauth.py](../local/runtime/oauth.py) | Mới | OAuth client credentials cache/refresh có TTL, atomic token file và fail closed khi token hết hạn. |
| [local/tests/test_operator_safety.py](../local/tests/test_operator_safety.py) | Mới | Tests authored cho credential idempotency, private context, dirty source identity, credential-free Git URL và base-image pins; chưa chạy. |
| [local/versions/app-source.lock.json](../local/versions/app-source.lock.json) | Mới | Snapshot SHA/Git revision của current app interfaces/Dockerfiles; không là build/deploy evidence. |
| [local/versions/k3d-v1alpha5.schema.json](../local/versions/k3d-v1alpha5.schema.json) | Mới | Bản official k3d config schema vendored có SHA provenance. |
| [local/versions/platform.lock.json](../local/versions/platform.lock.json) | Mới | OCI/tool/source pins; Keycloak/Argo/kubectl metadata ghi nhận read-only, chưa runtime validation. |
| [localdev/__init__.py](../localdev/__init__.py) | Mới | Package local tooling, không có import-time cluster action. |
| [localdev/__main__.py](../localdev/__main__.py) | Mới | Entrypoint python -m localdev cho operator infrastructure. |
| [localdev/checks.py](../localdev/checks.py) | Mới | CI offline source policy, app interface/source pins, local contracts và protected-production fingerprints. |
| [localdev/cli.py](../localdev/cli.py) | Mới | CLI operator: cluster lifecycle, actual image build/import, secrets, Argo bootstrap, owner migration/grants/provision/ordering, release preparation, broker smoke và approved training Job. |
| [localdev/common.py](../localdev/common.py) | Mới | Private-state/context guard, argument-array subprocess, source snapshot identity và kiểm base images bằng digest. |
| [localdev/credentials.py](../localdev/credentials.py) | Mới | Sinh và giữ credentials/TLS, tạo scoped Kubernetes Secrets qua stdin, tách owner và runtime DB logins. |
| [versions/local-contracts.lock.json](../versions/local-contracts.lock.json) | Mới | SHA lock các schema local mới; bản sao giữa hai repo phải byte-identical. |
| [versions/local-production-baseline.lock.json](../versions/local-production-baseline.lock.json) | Mới | Fingerprints các file AWS/production hiện hữu để CI phát hiện local work sửa nhầm phạm vi. |
