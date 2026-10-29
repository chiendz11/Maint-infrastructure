# Đồng bộ source local và public remote — 29/10/2026

## 1. Ba repo và nguồn Git để Argo CD theo dõi

- App: https://github.com/chiendz11/MaintAI — source ứng dụng và Dockerfile.
- GitOps: https://github.com/chiendz11/MaintAI-gitops — desired state của platform,
  monitoring và app; có roots riêng cho local và production.
- Infrastructure: https://github.com/chiendz11/Maint-infrastructure — AWS Terraform,
  local k3d, private credentials và bootstrap Argo CD.

Settings mẫu infrastructure dùng
`https://github.com/chiendz11/MaintAI-gitops.git`, revision `main`. Argo chỉ đọc
commit đã push. Có remote không đồng nghĩa cluster đã tạo hoặc workloads đã bật.

## 2. App revision được đối chiếu

Commit app: `7c05489f705e0f55c45d03252869e27760da1c25`. Commit này gồm Storage catalog0.2.1,
ML của PR15, RAG của PR16 và digest pins của PR19. ML/RAG dùng official Python
OCI indexes theo digest; giữ Python3.12 cho ML và Python3.11 cho RAG.

Hai bản app-source lock phải giống từng byte:

- GitOps: `config/local/app-source.lock.json`.
- Infrastructure: `local/versions/app-source.lock.json`.

Lock giữ Git SHA và SHA256 các interface, entrypoints, requirements và Dockerfiles
đã review. Không dùng hash của working tree chưa commit để giả một release.
`docs/application-source-lock.json` giữ import audit cũ và mục active có SHA mới;
những tên file v1.3 ở phần import là lịch sử, không là target local hiện tại.

CI checkout chính xác commit app trong lock và so sánh các file đã chọn. Trước
build app, CLI infrastructure cũng kiểm commit và checksum. Checkout khác SHA hoặc
sửa interface sẽ bị từ chối. Khi app tiến lên, review thay đổi rồi cập nhật đồng
thời hai locks; không tự lấy latest hoặc chỉ sửa checksum để bỏ qua khác biệt.
Dirty builds vẫn ghi rõ snapshot, nhưng không bỏ qua interfaces đã khóa.

## 3. ML baseline và dữ liệu local

GitOps cấp `MAINTAI_LOCAL_ONLY=1` và
`MODEL_DIR=/local/models/logreg-baseline-v0`. Mount `/local/models` ánh xạ tới
`Maint-infrastructure/local/.local/data/models` trên laptop.
Bundle gồm `pipeline.joblib`, `metadata.json`, `evaluation.json`,
`drift_reference.json`. Version thật: `logreg-baseline-v0`, preprocessing
`onehot-standardscaler-v0`; không cần MLflow để đặt tên version local.

AI4I được tải bằng downloader có checksum của Sensor, ở
`MaintAI/sensor/data/ai4i2020.csv`; copy dữ liệu nguyên bản vào
`Maint-infrastructure/local/.local/data/datasets/ai4i2020.csv` để khớp mount k3d.
CSV, model binaries, credentials, TLS keys và private receipts không commit.

Worker vẫn cần policy do nhóm chốt và full model identity khớp artifact/image.
File thiếu không được thay bằng hash hoặc MLflow run giả. ML local prototype
không có JWT provider production; runtime review và network boundary vẫn cần
được operator xác nhận trước khi enable.

## 4. RAG sau PR16

RAG có HTTP API, probes, migration CLI và knowledge ingestion CLI. Muốn chạy thật
cần: Secret DATABASE_URL; schema knowledge_db; PDF đã ingest; embedding cache;
OLLAMA_BASE_URL tới Ollama trên laptop; model Ollama đã tải. Có thể khai báo URL
host bridge và model names trong component env; database URI chỉ lấy từ Secret.
Không dùng localhost của Pod để chỉ Ollama trên laptop.

`owner_input_required` trong catalog tiếp tục yêu cầu review runtime inputs và
image receipts, không có nghĩa ML/RAG còn là skeleton. Copilot Business M7,
Drift adapter và training vẫn là phần việc riêng; publish source không hoàn tất
những luồng đó.

## 5. Trình tự sau khi source đã push

1. Clone ba repo cạnh nhau; app checkout phải đúng SHA trong lock.
2. Đọc runbook `Maint-infrastructure/local/README.md`; init private settings và
   chuẩn bị dữ liệu, artifact, policy/identity, auth cùng tài nguyên laptop.
3. Operator tạo k3d, build/import platform images, chuẩn bị GitOps platform diff,
   push GitOps rồi bootstrap Argo. Source publication không tự chạy các bước này.
4. Build/import app images đúng lock; chạy owner migrations/grants/provisioning
   và activate ordering sau khi đủ điều kiện.
5. Review profile, checksum inputs và actual image receipts; prepare app desired
   state, commit/push GitOps; Argo mới đồng bộ workloads.
6. Sensor bắt đầu PAUSED. Chỉ Resume qua Simulator UI sau khi downstream ready;
   kiểm tra telemetry/prediction/alert trên Business UI bằng dữ liệu thật.

Mọi app trong profile mẫu vẫn disabled. CI source/unit/render, image build,
Argo health, full pipeline và benchmark là các bằng chứng khác nhau. Những file
AWS/production được fingerprint bảo vệ vẫn giữ nguyên bytes trong lần đồng bộ này.
