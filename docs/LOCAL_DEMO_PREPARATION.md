# Chuẩn bị Groq và knowledge cho demo local

Quyết định30/10/2026. App sở hữu client Groq, `embedding-lock.json`,
`knowledge-demo.json`, migration/ingestion và helper identity local. GitOps sở hữu
RAG environment, Secret references, writable cache PVC và template Job.
Infrastructure cấp Secret values, build/import image và chạy owner operation.
Không deploy lại production, không đưa dữ liệu/key vào Git.

## Credential và cấu hình

Operator tạo key mới và lưu tại
`Maint-infrastructure/local/.local/secrets/groq-api-key`, mode0600; directory0700.
Không lấy key đã lộ trong chat/log làm fallback. Init không tạo key giả.
`python -m localdev groq-secret` ở infrastructure đọc file và cấp Secret
`rag-groq` qua stdin; bootstrap cũng cấp nếu file đã tồn tại. Thiếu key không
chặn bootstrap nền tảng, nhưng RAG không được enable cho đến khi có credential.

Deployment chỉ chứa `secretKeyRef` tới `GROQ_API_KEY`; không chứa giá trị key.
Đổi key cần chạy lại secret command và restart RAG. CI dùng fixtures, không cần
provider secret. Key bị từ chối không tự fallback Ollama. Pod cần HTTPS/DNS tới
api.groq.com. Model ID/timeout/output budget được chọn tại rag-runtime.json.

## Model identity không MLflow

Sau khi build ML và Worker từ cùng app commit đã khóa, chạy trong infrastructure:

```bash
.venv/bin/python -m localdev model-identity
```

Tool đối chiếu image receipt với Docker store và lấy RepoDigest OCI thật; không
đổi config ID thành manifest digest. Worker helper kiểm bundle, dataset/split,
feature schema rồi tạo private `data/fixtures/model-identity.json` và evidence.
`mlflow_run_id=not-recorded:local-demo` công khai rằng không có MLflow run.
Manifest dataset được tái dựng và ghi rõ không phải approved training manifest.
Policy/model/quality approval không được suy ra từ hash hoặc marker local.
Engine thiếu OCI RepoDigest phải tạo/export/publish image hợp lệ trước.

## Chuẩn bị knowledge sau khi nền tảng sẵn sàng

1. Argo sync PostgreSQL/pgvector và PVC `local-rag-embedding-cache` từ platform root.
2. Build/import RAG image đúng app lock.
3. Chạy `.venv/bin/python -m localdev prepare-rag` trong infrastructure.
4. Job dùng knowledge-owner Secret, không cần Groq key; migrate, tải/load đúng
   revision MiniLM, kiểm PDF hash, ingest và kiểm retrieval/citation metadata.
5. Chạy lại để kiểm idempotence; stored chunks giữ nguyên, inserted=0.
6. Receipt private `rag-knowledge-receipt.json` ghi image/source, chunks và IDs
   retrieval. Khi prepare apps, infrastructure bắt buộc receipt khớp image RAG.

Job và API dùng cùng PVC/cache path/model revision. Job được tải model; API dùng
MODEL_LOCAL_FILES_ONLY=true. Root filesystem vẫn read-only, chỉ cache và /tmp
ghi được. PVC tồn tại độc lập với Deployment; không prune/xóa PVC khi rollout.
Job là operator operation một lần, không là service thường trực hoặc mutation
ẩn trong startup. Knowledge failure không chặn Sensor/ML/Alert pipeline.

Cùng document ID/version nhưng PDF hoặc embedding khác phải fail; chọn version
mới hoặc review migration. Không tự xóa/backfill knowledge cũ. Chạy seed không
gọi Groq, không chứng minh M7 Copilot/Business UI đã tích hợp hoặc E2E đã pass.

## Versioning và evidence

App merge trước; hai source locks và risk-policy selector trỏ đúng squash SHA
trên main. App interfaces/PDF/embedding/preparation helper đều có SHA256 trong
lock. Giữ contract/schema/production fingerprint cũ nguyên bytes. CI source,
actual image, real embedding/pgvector, live Groq và UI E2E là các mức riêng.

## Kiểm chứng local ngày30/10/2026

Source/unit: RAG66 tests, Processing/Business288 tests (không integration),
GitOps31 tests và Infrastructure17 tests. CI remote của đúng commit được ghi
riêng khi PR hoàn tất. Các fingerprint production/contracts được kiểm nguyên vẹn.

Đã chạy real MiniLM384 revision đã khóa với PostgreSQL17/pgvector0.8 qua một
container verification riêng: PDF46 trang tạo106 chunks; lần đầu inserted106,
lần hai inserted0 và stored106; retrieval trả chunk IDs96/35/23. Knowledge
owner là role riêng, không superuser. Không gọi Groq để tạo completion trong
bài kiểm chứng này. Private report/log/cache nằm trong infrastructure .local.

Đây là kiểm chứng dữ liệu thật trong Docker, **không là receipt của DB/PVC trên
k3d**. Trên cluster đích vẫn phải chạy prepare-rag để Job dùng đúng cache PVC và
ghi receipt theo image đã import. Không copy receipt verification thành receipt
cluster hoặc bật các cờ owner-operation khi chưa thực hiện.
