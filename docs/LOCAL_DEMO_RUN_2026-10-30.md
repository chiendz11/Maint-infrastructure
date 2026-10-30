# Báo cáo chạy demo MaintAI trên laptop — 30/10/2026

Đây là kết quả chạy thật trên cluster `maintai-local`, không phải kết luận rút ra
từ Dockerfile hoặc trạng thái CI. Phạm vi là 5 máy giả lập, mỗi máy 1 reading/giây,
telemetry/prediction trên Business UI, điều khiển Simulator, Alert lifecycle,
raw archive vào MinIO và một lời gọi RAG/Groq trực tiếp.

## 1. Source và môi trường đã sử dụng

| Thành phần | Source đã dùng |
| --- | --- |
| App nền | `chiendz11/MaintAI`, commit `5b4664bb24e9f107c00a83e1faffb72fc5c1f4e3` |
| Bản sửa Kafka | Nhánh `fix/kafka-serial-prefetch`, commit `2df0a914287a86f3500731ba05a2ba866bbee160`, SDK0.3.1 |
| GitOps local | Nhánh `demo/local-k3d`; ba Application theo `environments/local/{platform,observability,apps}` |
| Infrastructure local | Nhánh `demo/local-k3d`; cluster, private kubeconfig, Secrets, Argo bootstrap và owner Jobs |

Bản sửa SDK đã push và mở [PR22](https://github.com/chiendz11/MaintAI/pull/22),
chưa merge vào `main` trong đợt chạy này. Business API/Consumer và Storage dùng
image đã build từ commit sửa lỗi; các component còn lại giữ receipt của source
nền. Không gán cùng một source SHA giả cho mọi image. Source locks ở hai repo
platform đã đồng bộ với source được review; từng image vẫn có receipt riêng.

Local dùng k3d5.9.0, Kubernetes1.35.5, Argo CD3.2.0, Kafka KRaft một broker,
PostgreSQL17/pgvector và MinIO. Không provision AWS trong lần chạy này.

## 2. Các bước đã thực hiện

### Bước 1 — Chuẩn bị dữ liệu, model và credential

- Đặt AI4I CSV10.000 dòng trong private local data. Simulator chỉ đưa sáu feature
  allowlist vào pipeline; các machine ID là danh tính máy giả lập.
- Kiểm bundle `logreg-baseline-v0`: pipeline, metadata, evaluation và drift reference.
- Tạo full model identity từ checksum thật và OCI image identity. Marker
  `not-recorded:local-demo` thể hiện chưa có MLflow run; không phải run ID giả.
- Risk policy được chọn từ app catalog, kiểm version/hash rồi tạo ConfigMap.
  Không tạo một bản policy chỉnh tay thứ hai trong infrastructure.
- Lưu Groq key vào file private mode0600 và cấp vào Secret `rag-groq`.
  Deployment RAG nhận `GROQ_API_KEY` qua `secretKeyRef`; Git không chứa key.

Dữ liệu nằm trong `local/.local/data/`. Credential được tạo/lưu trong
`local/.local/credentials.json`; key Groq ở `local/.local/secrets/groq-api-key`.
Không đưa nội dung các file này vào báo cáo, Git hoặc câu lệnh có thể lộ key.

### Bước 2 — Build và import image

Build các app image và helper image từ source đã khóa, ghi source Git SHA,
snapshot hash, Dockerfile hash và Docker image ID thật vào `local/.local/receipts/`.
Sau đó import image vào đúng `k3d-maintai-local`.

Đợt local này dùng image đã import với `imagePullPolicy: Never`. Chưa cần ECR
để chạy demo. Registry publication là một đường phát hành khác, không được coi
là đã thực hiện chỉ vì image đã có trong Docker trên laptop.

### Bước 3 — Tạo cluster và bootstrap Argo CD

Cluster dùng private kubeconfig `local/.local/kubeconfig`, context
`k3d-maintai-local`; không đổi current context của người dùng. Infrastructure
bootstrap Argo CD và ba Application, còn manifests platform/app do GitOps quản lý.

Argo đọc nhánh đã push `demo/local-k3d`. Nó không đọc các chỉnh sửa chưa commit
trên laptop. Các workload không được apply lặp lại từ một repo khác.

### Bước 4 — Khởi tạo các DB owner và máy giả lập

Đã chạy và kiểm thành công sáu owner Jobs:

1. Migration Processing.
2. Migration Business.
3. Cấp runtime grants Processing.
4. Cấp runtime grants Business.
5. Provision M-001 đến M-005 vào registry.
6. Activate ordering sau khi xác nhận không còn legacy writer đang chạy.

Worker/Relay/Business sử dụng các login có phạm vi riêng. Không dùng kết nối
superuser làm runtime credential hoặc cho Business truy vấn trực tiếp Processing DB.

### Bước 5 — Chuẩn bị knowledge cho RAG

Chạy owner Job `prepare-rag` trên cluster đích, dùng cache PVC và knowledge owner:

- Load MiniLM multilingual revision đã khóa, vector384 chiều.
- Kiểm checksum PDF46 trang, migrate knowledge schema và ingest106 chunks.
- Kiểm vector retrieval và metadata cần cho citations.
- Ghi receipt gắn với image/source thật của RAG trên cluster đích.

Job này là Job thứ bảy đã hoàn tất. API RAG dùng cùng cache PVC, không phải tải
model embedding trong mỗi request. Generation gọi Groq với `openai/gpt-oss-20b`;
không chạy Qwen/Ollama trên laptop trong cấu hình demo này.

### Bước 6 — Kiểm tra đăng nhập và cấp quyền

Đăng nhập thực qua Keycloak bằng trình duyệt, dùng Authorization Code/PKCE.
Business và Simulator có client, audience và đường API riêng. Access token có
subject, roles và machine scope; không tắt JWT verification để vượt qua lỗi auth.

CA phát triển của Keycloak được thêm vào NSS trust store của người dùng để
Chromium xác minh HTTPS local. File CA public và receipt được giữ trong private
local state; không dùng `ignoreHTTPSErrors` để thực hiện bài kiểm tra trình duyệt.

### Bước 7 — Bật app và chạy các kịch bản

Sau khi đủ image/artifact/auth/owner-operation evidence, chuẩn bị reviewed profile,
commit/push desired state và để Argo rollout 12 app runtimes. Simulator bắt đầu
PAUSED; các thao tác tiếp theo được thực hiện qua UI thật.

Luồng đã quan sát:

```text
Simulator UI -> Sensor -> Ingestion -> sensor.readings
                                      |             |
                                      v             v
                                Processing       Business telemetry
                                  -> ML               |
                                  -> Risk             v
                                  -> DB/Outbox    Business DB -> REST/SSE -> UI
                                      |
                                      v
                                Outbox Relay
                                  -> inference.results / alert.signals
                                      -> Business projection / Alert lifecycle

sensor.readings -> Storage Consumer -> MinIO raw object + manifest
```

## 3. Kết quả kịch bản

| Kiểm tra | Kết quả quan sát được |
| --- | --- |
| Normal | Có telemetry và prediction thật, Processing COMPLETED, model `logreg-baseline-v0`; một snapshot có cùng source event, telemetry age545ms và prediction age448ms |
| Pause riêng M-001 | Sequence giữ796 qua hai lần đọc; M-002 vẫn tăng799 ->803 |
| Resume M-001 | Tiếp tục sequence797, không reset stream |
| Critical | Tạo alert mới cho M-002, severity CRITICAL, risk_score0.9635227210665391 qua ML/risk thật |
| Recovery | Chấp nhận điều khiển cả5 máy; alert đang mở không tự bị đóng |
| Lifecycle | UI thực hiện ACK -> START -> RESOLVE; audit có CREATED, ACKNOWLEDGED, IN_PROGRESS, RESOLVED |
| Feedback | Ghi nhận feedback từ UI, verdict INCONCLUSIVE và recommendation NOT_AVAILABLE vì Business Copilot chưa tích hợp |
| Degradation | M-005 chuyển scenario thành công, sequence1298 ->1303 và có prediction mới; chưa đo đầy đủ ramp300 readings |
| Raw archive | Một snapshot có3970 raw objects và3970 manifests; bucket versioning Enabled; đã đọc đúng object VersionId và kiểm SHA-256/frame count |
| RAG trực tiếp | HTTP200, dịch vụ trả GROUNDED, 10 bước checklist, 3 citations; provider Groq và3 chunks retrieval thật |

Các số đo age ở trên là một snapshot, không phải p95 latency hoặc benchmark100 máy.
Normal nghĩa là không thêm biến đổi scenario vào AI4I; bản thân AI4I có các dòng
rủi ro cao, nên Normal không bảo đảm toàn bộ readings đều tạo prediction NORMAL.
Tên Critical cũng không ép đầu ra: alert chỉ xuất hiện khi model/policy thật thỏa điều kiện.

RAG được gọi bằng evidence của một alert thật, nhưng gọi trực tiếp endpoint RAG.
Chưa có bằng chứng Business UI/Copilot M7 đã gọi và lưu brief; UI hiện vẫn hiển thị
UNAVAILABLE ở panel này. Không gọi đây là tích hợp Copilot hoàn chỉnh.

## 4. Những lỗi runtime đã sửa

| Vị trí | Lý do và cách sửa |
| --- | --- |
| k3d config | Bật server load balancer cần cho API proxy port mapping |
| RAG cache PVC | Chuyển sync wave về0 để WaitForFirstConsumer không chặn toàn bộ platform sync |
| Keycloak runtime | Giới hạn JVM heap và tăng memory limit để tránh OOM trong startup augmentation |
| TLS/HTTP bridge | Proxy tự đặt forwarding headers theo kết nối thật; không tin header forwarding do caller gửi |
| OAuth helper | Không gửi scope rỗng; chỉ gửi scope khi được cấu hình |
| Keycloak realm | Bổ sung native basic scope và rollout service clients để access token có sub |
| Groq runtime | Chọn model thực sự được tài khoản/provider cung cấp thay vì ID unavailable |
| SDK ConsumerRunner | SDK0.3.1 dùng bounded prefetch64/32, một handler; bỏ pause tất cả partition sau từng record gây backlog và phục vụ máy không đều |
| Local Relay config | Giảm OUTBOX_POLL_INTERVAL_MS250 ->10; nhịp cũ làm DB outbox tăng khi5 máy chạy liên tục |

Không reset offsets, xóa inbox/outbox hoặc bịa prediction/alert để tạo kết quả demo.
Chỉ các ConfigMap hash cũ đã xác minh không còn workload đang chạy tham chiếu mới
được dọn; giữ nguyên PVC, DB, Secrets và cơ chế Argo prune=false.

## 5. Các kiểm tra đã chạy

- SDK/Processing unit:86 passed.
- Kafka/PostgreSQL integration thật trong Compose riêng:25 passed, gồm regression
  backlog nhiều partition. Các container/volume chỉ dành cho lần test này đã dọn.
- Storage regression:78 passed,2 optional integrations skipped ở lệnh này.
- Business subset:4 passed,17 DB tests skipped ở lệnh subset; không gán chúng là DB integration pass.
- GitOps32 unit tests và Infrastructure22 unit tests passed.
- Kiểm source locks, contract/production fingerprints, document hashes và local refs passed.
- [Full app push CI tại đúng commit](https://github.com/chiendz11/MaintAI/actions/runs/41001003039) passed.
- Browser/OIDC và core pipeline thực trên k3d passed, có screenshots/private receipts.

Sau tuning, kiểm tra thêm120 giây với5 máy, lấy24 snapshots/máy cách nhau5 giây:
120/120 snapshots có telemetry/prediction age dưới5 giây. Giá trị lớn nhất quan
sát được là telemetry1.030425 giây và prediction1.084452 giây. DB outbox đã về0.
Đây là tuổi dữ liệu tại thời điểm đọc API, không phải phép đo p95 event-to-browser.

Chi tiết chạy liên tục được ghi riêng trong
`local/.local/continuous-demo-receipt.json`. Đây là kiểm tra5 máy với snapshot
định kỳ, không phải kiểm chứng tải100 máy hoặc HA của AWS.

## 6. Mở và tiếp tục demo

| Màn hình | URL local |
| --- | --- |
| Business UI | http://127.0.0.1:18080 |
| Sensor Simulator UI | http://127.0.0.1:18081 |
| Grafana | http://127.0.0.1:13000 |
| Prometheus | http://127.0.0.1:19090 |
| MinIO Console | http://127.0.0.1:19001 |
| Argo CD, khi port-forward đang chạy | https://127.0.0.1:18443 |

Business/Simulator đăng nhập user `administrator`; đọc password tại khóa
`users.administrator` trong file credentials private. Grafana có password riêng
trong cùng file. Argo CD dùng user `admin`; password riêng đã lưu tại
`local/.local/secrets/argocd-admin-password`. Argo UI dùng chứng chỉ phát triển
của Argo; Keycloak dùng CA local đã chuẩn bị. Không truyền Groq key vào trình duyệt.

Để xem trạng thái hoặc tạm dừng toàn cluster, chạy tại infrastructure repo:

```bash
.venv/bin/python -m localdev status
.venv/bin/python -m localdev stop
.venv/bin/python -m localdev start
```

Để mở lại Argo UI khi phiên port-forward đã đóng:

```bash
.venv/bin/python -m localdev forward argocd
```

Sau các kiểm tra, cả5 máy được đưa về scenario normal và giữ RUNNING để tiếp tục
demo. Có thể Pause từng máy trên Simulator UI khi không muốn sinh thêm dữ liệu.
Các số liệu, screenshots, JSON evidence và log chi tiết nằm trong `local/.local/`;
không copy credential hoặc toàn bộ private runtime data vào Git.

## 7. Phạm vi chưa được chứng minh

Chưa chạy benchmark100 máy, multi-node HA, phục hồi mất mạng/crash toàn pipeline,
đầy đủ ramp300 readings của Degradation/Recovery hoặc vòng đời training/promotion.
MLflow, training và Drift không được bật trong reviewed demo profile này.
M6 History/Export và Business Copilot M7 không được coi là hoàn thành từ các
kết quả trên. Model/policy đang dùng là baseline/demo, chưa là approved production release.
