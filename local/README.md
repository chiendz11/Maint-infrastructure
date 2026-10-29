# MaintAI local — k3d bootstrap và Argo CD

Phần local phiên bản **1.0.0**, bổ sung vào repo infrastructure hiện có. `terraform/`
vẫn sở hữu AWS; `local/` không gọi Terraform hoặc AWS. GitOps sở hữu desired state
trong cluster, gồm Kafka/PostgreSQL/MinIO, monitoring và ứng dụng. Hai ZIP chỉ là
nguồn tham khảo; không giải nén đè, không dùng entrypoint hoặc config DTO cũ.

**Trạng thái 29/10: source đã public; CI đã chạy source/unit checks và xác minh
app revision/checksums.** Xem [CI](https://github.com/chiendz11/Maint-infrastructure/actions/workflows/ci.yml)
và [source sync](../docs/LOCAL_SOURCE_SYNC.md). Image builds, k3d, Argo bootstrap,
Terraform và E2E chưa được chạy trong đợt publication. Các lệnh dưới là runbook
cho operator, không phải lịch sử đã thực hiện. Pin metadata không chứng minh
image đã chạy hoặc phiên bản tương thích.

## 1. Bản đồ công việc

| Đường dẫn | Trách nhiệm |
| --- | --- |
| `local/config/k3d.yaml` | Một server, không agent; API127.0.0.1:6550, NodePorts chỉ bind host loopback, host storage/data mounts |
| `local/config/contract.json` | Namespace, context, ports, issuer và ba Argo source paths; bản sao byte-identical ở GitOps |
| `local/config/runtime-catalog.json` | Dockerfile/context/entrypoint/port/migration đúng source M5; mọi workload mặc định tắt |
| `local/versions/` | Tool/OCI/source pins, official k3d schema và app interface snapshot |
| `local/images/` | MinIO/mc build từ upstream source có SHA256, thay vì `latest` hoặc digest giả |
| `local/runtime/` | Adapter HTTP/TCP/TLS và OAuth token refresh; không chứa business logic hoặc ML giả |
| `localdev/` | CLI init/up/build/import/secrets/bootstrap/migrate/grants/provision/prepare |
| `local/tests/` | Tests sẽ chạy ở CI; chỉ kiểm private state/provenance, không gọi cluster |
| `local/.local/` | State/private settings, credentials, TLS keys, data, receipts; gitignored |

Không có lệnh implicit apply ứng dụng trong `up`. Không tự tạo repo GitHub,
commit/push, thay current-context, promote model hoặc phát cảnh báo giả.

## 2. Chuẩn bị trên laptop

Cần Docker Engine, đúng k3d pin5.9.0, kubectl tương thích Kubernetes1.35, OpenSSL,
Git và Python3.12. Dự trù laptop8 CPU/16GB RAM và disk trống; đây là ngân sách gợi
ý, không phải benchmark. Full ML/RAG/training có thể cần thêm tài nguyên.

Từ root `Maint-infrastructure/`:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r local/requirements.lock
.venv/bin/python -m localdev init
```

`init` chỉ tạo private files; chạy lại giữ nguyên credentials. Sửa
`local/.local/settings.json`: kiểm tra GitOps URL
`https://github.com/chiendz11/MaintAI-gitops.git`, revision `main`, đường dẫn
app/GitOps checkout và machine_count (mặc định5, giới hạn100 cho profile).
Settings mẫu đã có URL remote thật; `init` giữ nguyên settings riêng nếu đã tồn tại.
Source phải được commit trước khi build; desired state phải push trước khi Argo
đọc được. Xem [source sync](../docs/LOCAL_SOURCE_SYNC.md) để đối chiếu revision app.

CLI không tự cài binaries hoặc ghi vào ~/.kube/config. Nếu cluster `maintai-local`
đã do tooling khác tạo và chưa có marker của bootstrap này, `up` từ chối nhận
quyền quản lý. Xuất/backup dữ liệu và chốt cutover trước; không chạy hai bộ tooling
cùng quản lý cluster đó.

## 3. Khởi tạo nền và release platform

```bash
.venv/bin/python -m localdev up
.venv/bin/python -m localdev build-platform
.venv/bin/python -m localdev import-images --component minio --component mc --component dev-tools
.venv/bin/python -m localdev prepare platform
```

`up` chỉ tạo cluster/kubeconfig riêng, chưa apply platform/app. `build-platform`
build từ infrastructure source đã commit; source dirty bị chặn trừ khi operator
chọn `--allow-dirty`, khi đó receipt ghi rõ dirty và snapshot hash. Không dùng
receipt dirty như provenance production.

`prepare platform` sửa duy nhất `MaintAI-gitops/environments/local/platform/`
để thay placeholders bằng aliases `image-<actual Docker image ID>`. Nó không
commit/push. Review GitOps diff và commit/push nhánh đúng settings, sau đó:

```bash
.venv/bin/python -m localdev bootstrap-argocd
.venv/bin/python -m localdev status
```

Bootstrap tạo secrets local, cài Argo từ manifest khóa SHA256, thay images upstream
bằng OCI digest đã ghi nhận và tạo AppProject chỉ cho remote repo đã chọn, đích
`maintai-local`. Ba Applications đọc riêng platform/observability/apps; không đọc
production roots. `selfHeal=true`, `prune=false` mặc định. Chưa tự đồng bộ private
repository credentials: với repo private, operator phải cấp repository Secret
cho Argo ngoài Git trước khi sync.

Platform tạo PostgreSQL17 + pgvector0.8, bốn topics12 partitions, Kafka4 KRaft
một broker, MinIO với bảy bucket versioned, Keycloak dev và TLS identity gateway.
Monitoring là Application riêng. Bootstrap Jobs chạy sau datastores bằng sync
waves và chỉ làm platform initialization; owner SQL migrations nằm ở bước sau.

## 4. TLS, đăng nhập và service credentials

Local issuer là `https://127.0.0.1:18490/realms/maintai`. CA được tạo dưới
`local/.local/tls/ca.crt`; operator phải tin cậy CA này trong browser trước login.
CLI không tự sửa trust store hệ điều hành/browser và không tắt certificate verify.
Leaf certificate90 ngày; renewal phải giữ CA, thay leaf/Secret và restart các
adapter pods theo một thay đổi vận hành được review. Không xóa CA/credentials
khi muốn giữ Keycloak/database state.

Keycloak native UI/server là dev-only, persistent H2 trên PVC, không phải Auth
Service do app tự viết hoặc HA production. Import realm dùng placeholders lấy
client secrets/user passwords từ Kubernetes Secrets. Passwords của `viewer`,
`technician`, `administrator` và Keycloak admin nằm trong private credentials.json;
xem bằng editor local, không paste vào Git/CI logs. Realm đã tồn tại không bị
import lại; thay đổi realm schema/roles cần migration/admin operation riêng.

Business và Processing Read vẫn kiểm signed JWT + machine scope. M5 Consumer/API
có client `maintai-processing`, token BUSINESS_SERVICE đúng audience; token agent
làm mới `/tokens/processing.jwt` trước expiry. Worker registry adapter lấy token
VIEWER theo machine scope vì registry hiện chia sẻ Business read endpoint; nó
không mang quyền mutation. Sensor dùng OAuth client credentials, Control API
vẫn JWT/role/scope. Không dùng `AUTH_ENABLED=false` để giả định auth đã tắt.

Business/Read test profiles chỉ chấp nhận loopback. Local adapter nối loopback
với DNS services và chỉ inject service bearer ở route registry/ML của Worker.
Adapter không retry request mutation. JWT issuer có HTTPS; JWKS nội bộ của
Business/Read dùng loopback HTTP tới đúng Keycloak trong profile dev. Sensor có
HTTPS bridge và CA mount. Đây là compatibility layer có chủ đích, không phải
production networking hoặc việc nới lỏng guards của shared profile.

## 5. Build app, owner operations, bật pipeline

```bash
.venv/bin/python -m localdev build --component ingestion-api --component processing-worker --component processing-read-api --component processing-outbox-relay --component business-api --component business-consumer --component storage-consumer --component sensor --component frontend --component simulator-ui
.venv/bin/python -m localdev import-images
.venv/bin/python -m localdev migrate
.venv/bin/python -m localdev grants
.venv/bin/python -m localdev provision
.venv/bin/python -m localdev activate-ordering --legacy-writers-drained
```

Migrations gọi đúng `maintai-processing-migrate upgrade` và
`maintai-business-migrate upgrade`, với hai env owner DB riêng. Grants dùng chính
helper trong owner images; runtime API/Consumer/reader/worker/relay có logins và
quyền riêng, không dùng owner credential để chạy app. `provision` gọi Business
owner CLI với machine manifest đã tạo theo machine_count. Ordering activation
là bước explicit; fresh DB khác với migration một DB đã có source cursors/backlog.
Không dùng flag drained nếu writers thực sự chưa dừng. Không reset inbox/outbox.

Đặt AI4I tại `local/.local/data/datasets/ai4i2020.csv`, policy/identity tại
`data/fixtures/`, model bundle tại `data/models/`. Chúng không được tự phát sinh từ
live data. Model identity phải khớp image/model thực của ML owner. Checksum file
được kiểm ở bước prepare và init container trước khi app khởi động.

ML inference và RAG đã có Dockerfile chạy service, được pin Python base digest
trong app PR19. Local ML dùng `MAINTAI_LOCAL_ONLY=1` và
`MODEL_DIR=/local/models/logreg-baseline-v0`; đây là baseline local, không có JWT
provider production. RAG cần DB schema, knowledge đã ingest, embedding cache và
Ollama/model trên laptop. Hai component vẫn cần runtime review và receipts thật.
Training Dockerfile còn placeholder; Drift còn cần pin base/review adapter; MLflow
cần reviewed base/server/SDK pins. Build từ chối FROM chưa khóa digest và app
checkout khác source lock. `--allow-dirty` chỉ ghi nhận thay đổi source ngoài
các interface đã khóa; không bỏ qua app revision hoặc checksum review.

Copy `MaintAI-gitops/profiles/local.example.json` thành một profile review được.
Bật components thật, khai báo SHA256 các input files và đánh dấu đúng các owner
operations đã hoàn tất. Dùng:

```bash
.venv/bin/python -m localdev prepare apps --profile /absolute/path/to/reviewed-local-profile.json
```

Review/commit/push GitOps diff. Argo mới nhận desired state đó. Sensor luôn bắt
đầu PAUSED; Resume qua Simulator UI sau khi downstream sẵn sàng. Không coi cờ
attestation là bằng chứng đã test: đó là quyết định operator, cần đối chiếu Job
history/health/acceptance thực tế.

## 6. URLs và kiểm chứng về sau

| UI/dịch vụ | Địa chỉ host |
| --- | --- |
| Business UI + Business /api | http://127.0.0.1:18080, sau khi bật frontend |
| Simulator UI + Sensor /api | http://127.0.0.1:18081, sau khi bật simulator-ui |
| Keycloak issuer/UI | https://127.0.0.1:18490 |
| Grafana | http://127.0.0.1:13000 |
| MLflow | http://127.0.0.1:15000, chỉ khi có image/review |
| Prometheus | http://127.0.0.1:19090 |
| MinIO S3/console | http://127.0.0.1:19000 / :19001 |

```bash
.venv/bin/python -m localdev smoke-kafka
.venv/bin/python -m localdev forward argocd   # https://127.0.0.1:18443
.venv/bin/python -m localdev forward kafka    # 127.0.0.1:19092, EXTERNAL listener
.venv/bin/python -m localdev forward postgres # 127.0.0.1:15432
```

Kafka smoke dùng topic tạm riêng, không ghi chuỗi lỗi vào sensor.readings.
Broker smoke/Pod Ready/Argo Synced không chứng minh DQ→ML→risk→Alert→UI. Cần nghiệm
thu riêng VALID/INVALID/ML unavailable, replay, lifecycle M5, restart và token
expiry. Local single-node không chứng minh AWS HA hoặc p95 cho100 máy.

## 7. Vòng đời, training và CI

`stop`/`start` giữ cluster; `delete --confirm-delete-cluster` xóa cluster nhưng
không tự xóa private credentials/data trên host. Host-backed state không thay
backup database/object store, và cần kiểm restore thực. Không prune PVC hoặc
bật retention cleaner trong M5. Token/private keys không được đưa vào release.

Training local là Job opt-in qua `submit-training --manifest ...`; đọc mẫu ở
GitOps `profiles/local-training.example.json`. Nó yêu cầu image đã import, real
entrypoint và approved dataset manifest theo bucket/key/VersionId/SHA256. Training owner phải tải đúng object version, kiểm checksum và quality gate; platform không tự giả kết quả đó. Không dùng drift/sensor event để
trigger retrain, không tự promote model. Model release vẫn cần thay desired state
được review; không tự dịch SQS/Argo Events production thành training local giả.

CI được thêm source/contract/private-state tests; GitOps thêm Kustomize render cho
local và production bằng kubectl khóa checksum. Chưa chạy các checks đó trong
lượt code-first này. Khi được yêu cầu kiểm chứng, chạy từng tầng offline → images
→ cluster/platform → owner jobs → app E2E; ghi evidence riêng từng tầng.
