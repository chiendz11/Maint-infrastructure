# Bật M6 History trên local k3d

Ngày 06/11/2026. Business và Processing Read API đã có code M6. Tài liệu này
triển khai cấu hình/credential/grants tại hai repo platform, dùng lại image app
đang chạy. Không thêm History service hoặc DB riêng.

## Luồng request

Browser -> Business History facade -> Processing Read API -> processing_db.
Raw history đọc catalog và object version đã kiểm từ MinIO. Read API dùng một
login chỉ SELECT dữ liệu nguồn và một login `processing_history_meta` chỉ được
CRUD các bảng metadata trong schema `history_meta`.

Business giữ private RSA signing key. Processing chỉ lấy public JWKS qua local
adapter; JWT delegation sống tối đa60 giây, có actor/machine scope và `azp` khớp
subject thật của service token Keycloak. Hai API có cursor keys độc lập.

## 1. Chuẩn bị khóa và subject

Tại root infrastructure, sau khi Keycloak local sẵn sàng:

```bash
.venv/bin/python -m pip install -r local/requirements.lock
.venv/bin/python -m localdev.history prepare
.venv/bin/python -m localdev.history seed
```

`prepare` tạo một lần RSA3072 và hai cursor keys32 bytes tại
`local/.local/secrets/history.json`, mode0600. Chạy lại giữ khóa. Nó lấy service
token qua HTTPS của Keycloak, kiểm RS256/issuer/audience/expiry/role trước khi
ghi subject vào public selector `MaintAI-gitops/config/local/history-runtime.json`.
Public selector không chứa private key hoặc cursor secret.

`seed` đưa ba bộ secret vào LocalStack Secrets Manager bằng stdin, rồi ESO tạo:

- `local-business-history-keys`: signing-key.pem và Business cursor-keys.json.
- `local-processing-history-keys`: Processing cursor-keys.json riêng.
- `local-processing-history-env`: metadata DB URL và credential MinIO riêng.

Nó cũng bổ sung đúng hai password mới vào bootstrap Secrets; không đổi password
hiện có của các service khác. Không sửa trực tiếp Secret do ESO quản lý.

## 2. Đồng bộ nền tảng và cấp quyền

Đưa source platform lên nhánh được Argo theo dõi. History selector ban đầu giữ
`enabled=false`. Sync platform để provision login mới và user/policy MinIO
`maintai-history`; sync app để ESO tạo các Secrets M6.

Với DB có dữ liệu, trước hết đối chiếu migrations: Business phải bao gồm
`business_0004_history_markers`, Processing phải bao gồm `processing_0004_catalog`.
Runtime không tự migrate. Owner migration hooks hiện có tiếp tục là nguồn quản lý
schema; không downgrade hoặc reset DB. Sau khi migrations/Secrets đã sẵn sàng:

```bash
.venv/bin/python -m localdev.history provision
```

Lệnh chạy owner Job từ digest image Read API thực đang chạy: tạo metadata role
nếu thiếu, cấp CONNECT, gọi helper `grant_metadata`, và cấp CRUD bảng marker
Business cho Business API. Nó không cấp metadata role quyền đọc/ghi nguồn hoặc
quyền ghi outcome/outbox, không xóa reading/prediction.

Policy MinIO chỉ cho đọc raw-sensor/raw-catalog trong bucket đã chọn tại
`MaintAI-gitops/config/local/history-runtime.json`, và ghi/đọc
prefix `history-exports/` trong `maintai-processed`; không cấp DeleteObject.

## 3. Build adapter và bật hai API

Commit source infrastructure trước khi build để receipt ghi source sạch:

```bash
.venv/bin/python -m localdev.history build-adapter
.venv/bin/python -m localdev import-images --component dev-tools
```

Ở GitOps:

```bash
../Maint-infrastructure/.venv/bin/python -m localdev.history \
  --enable \
  --adapter-receipt ../Maint-infrastructure/local/.local/receipts/dev-tools.json
```

Review rồi commit/push `config/local/history-runtime.json` và các manifests local.
Lệnh cập nhật hai API và cấu hình catalog của Storage Consumer, giữ các resource
Phase2 khác. Generator chuẩn
cũng gọi cùng hàm wiring, tránh mất M6 khi tái sinh manifests.

Business API có thêm các biến BUSINESS_HISTORY_* và mount Secret riêng.
Processing có PROCESSING_HISTORY_* cùng metadata credential riêng. Endpoint
JWKS nằm ở adapter có sẵn của Business, port18091 nội bộ; Read API gọi qua proxy
loopback, phù hợp guard của local-test. MinIO cũng được nối qua loopback của Read API.
Chỉ adapter của hai API được đổi image; không cần build lại app.

`PROCESSING_RETENTION_ENABLED=false` và `PROCESSING_CLEANER_DRY_RUN=true` được giữ
rõ ràng. Bật History không cho phép xóa dữ liệu nguồn.

## 4. Kiểm tra sau rollout

1. Hai Deployment Ready; ESO M6 báo SecretSynced.
2. Trong Business UI, chọn máy -> Lịch sử; chọn khoảng thời gian có dữ liệu.
3. Predictions trả200 và có records; Sensor readings có raw/catalog coverage.
4. Timeseries/charts trả200; kiểm cursor trang tiếp không trùng membership.
5. CSV nhỏ trả file thật. Export lớn/Parquet cần job/artifact đã SUCCEEDED.
6. Thiếu auth vẫn401, sai scope vẫn403; không dùng token browser gọi trực tiếp Read API.

Nếu raw trả503, kiểm tuổi/coverage của Storage catalog, quyền MinIO và đồng bộ
catalog metadata. Không bỏ checksum hoặc thay unavailable bằng danh sách rỗng.
Nếu History trả401, kiểm delegation issuer, kid/JWKS và service subject trước.

## Vận hành khóa

Giữ `history.json` qua restart và chia sẻ đúng Secret giữa replicas cùng API.
Khóa ký khác cursor keys; hai API cũng không dùng chung cursor secret. Khi thay
key/kid phải giữ public key cũ đủ thời gian token/cursor còn hiệu lực, cập nhật
selector và rollout có kiểm soát. Đổi Secret không tự làm process nạp lại khóa.

## 5. Khôi phục sau khi laptop/LocalStack khởi động lại

LocalStack hiện là môi trường giả lập Secrets Manager cho local. Các mục trong
Secrets Manager có thể không còn sau khi Pod LocalStack được tạo lại. Khi đó
Secret Kubernetes cũ vẫn tồn tại, nhưng ESO báo `SecretSyncedError` và Argo bị
chặn tại sync wave của ExternalSecret. Không tạo password mới để khắc phục lỗi này.

Chạy tại root infrastructure, dùng đúng các file private đã giữ từ lần dựng đầu:

```bash
.venv/bin/python -m localdev.secret_store
.venv/bin/python -m localdev.history seed
```

Lệnh đầu khôi phục các mục DB, Storage và Groq từ `credentials.json` cùng file
`secrets/groq-api-key`. Lệnh sau khôi phục các mục M6 từ `secrets/history.json`.
Payload đi qua stdin tới LocalStack của cluster được sở hữu; không đi vào command
arguments, Git hoặc output. Thiếu credential thì dừng, không thay bằng password
mặc định hoặc key giả. Script cũ `local/manifests/seed_localstack_secrets.py`
chuyển tiếp tới cùng implementation này.

Yêu cầu ESO đọc lại ngay thay vì chờ chu kỳ một giờ:

```bash
.venv/bin/python - <<'PY'
import json, time
from localdev.common import kube
for item in json.loads(kube('get', 'externalsecrets', '-o', 'json', capture=True))['items']:
    kube('annotate', 'externalsecret', item['metadata']['name'],
         'force-sync=' + str(time.time_ns()), '--overwrite', capture=True)
print(kube('get', 'externalsecrets', capture=True))
PY
```

Chờ tất cả ExternalSecret có `READY=True`, sau đó cho Argo retry/sync. Không chỉnh
trực tiếp các khóa runtime mà ESO đang quản lý vì ESO sẽ ghi lại từ store.

## 6. Xử lý archive khi Kafka dùng lại offset

Trong lần bật M6 ngày 06/11/2026, Storage Consumer cũ đã bị CrashLoop trước khi
bật History. Kiểm tra Kafka và object version thực tế cho thấy cùng
`topic/partition/offset` chứa hai event khác nhau giữa dữ liệu Kafka hiện tại và
bucket cũ. Archive từ chối ghi đè là hành vi đúng; bật History không sửa được xung
đột identity này.

Cách phục hồi đã chọn:

| Thành phần | Quyết định |
| --- | --- |
| Bucket cũ `maintai-raw` | Giữ nguyên toàn bộ objects, versions và manifests |
| Bucket raw hiện tại | `maintai-raw-c8c61d245736`, bật versioning |
| Căn cứ chọn tên | Hash của Kafka cluster ID và topic IDs thật, ghi ở `archive_lineage` |
| Group prefix mới | `local-m6-c8c61d245736-`, chỉ áp dụng Storage Consumer |
| Điểm bắt đầu | Earliest còn trong broker cho group mới; không reset group cũ |
| Processing/Business groups | Giữ nguyên; không chạy lại hiệu ứng prediction/alert |
| Read API | Đọc bucket mới; metadata index có source key riêng theo bucket/prefix |
| Xóa dữ liệu | Không xóa bucket, không truncate DB, không bỏ qua offset conflict |

Đây là chuyển namespace archive có chủ đích cho phiên Kafka hiện tại. Không tự
động đổi bucket mỗi lần restart, không đổi cluster/topic IDs bằng tên tùy ý, và
không dùng thao tác này để che mất dữ liệu broker đã hết retention. Lịch sử raw
trong bucket cũ vẫn được giữ nhưng **không tự gộp** vào raw history của bucket mới.
Processing history trong PostgreSQL vẫn được truy vấn như trước.

`archive_replicas` trong selector cho phép từ1 đến3 replica local; lần phục hồi
này dùng3 để xử lý backlog. Tất cả cùng nhóm theo vai trò, nên Kafka phân chia
partition giữa các replica. Catalog dùng CAS để publisher cũ không làm lùi frontier.
Không tăng partition hoặc đổi key máy. Có thể đưa về1 sau khi backlog đã bắt kịp;
review/push selector rồi chạy lại generator thay vì scale tay ngoài GitOps.

Storage Consumer được bật `STORAGE_CATALOG_ENABLED=true`. Hai consumer group
vẫn lưu accepted/rejected độc lập, chỉ commit offset sau khi object và manifest
đã lưu bền vững. Catalog mô tả receipt, phiên bản object, checksum và coverage của
partition. Chỉ bật hai History flags mà chưa có catalog thì chưa đủ xem raw.

Để kiểm tra tiến độ mà không in credentials:

```bash
.venv/bin/python - <<'PY'
import json
from collections import Counter
from localdev.common import kube
raw = kube('exec', 'deployment/storage-consumer', '-c', 'storage-consumer',
           '--', 'maintai-storage', 'catalog-inspect', capture=True)
catalog = json.loads(raw)
print('Generation:', catalog['generation_id'])
print('Coverage:', dict(Counter(p['status'] for p in catalog['partitions'])))
for p in catalog['partitions']:
    if p['topic'] == 'sensor.readings' and p['captured_log_end_offset']:
        print(p['partition'], p['indexed_next_offset'],
              p['captured_log_end_offset'], p['status'])
PY
```

Read API chỉ cho raw history hoạt động khi đủ12 partition accepted có coverage
`COMPLETE`, không có gap và generation còn mới trong120 giây. Trong lúc backfill,
503 raw history là trạng thái chưa sẵn sàng; không đổi thành200 với danh sách rỗng
hoặc sửa coverage bằng tay. Prediction history/biểu đồ risk có thể dùng trước.

## 7. Tránh Argo và HPA tranh nhau số replica

Bootstrap Argo hiện bỏ qua đúng trường `/spec/replicas` của bảy Deployment có HPA:
Business API, Frontend, Ingestion, ML chính, ML shadow, Processing Worker và RAG.
`RespectIgnoreDifferences=true` giữ quyền scale cho HPA khi sync resource khác.
Images, env, probes, volumes và tất cả trường khác vẫn được Argo quản lý.
Storage Consumer không có HPA nên số replica vẫn lấy từ GitOps selector.

`prune=false` vẫn được giữ. ConfigMap hash cũ không còn được tham chiếu có thể làm
Argo báo OutOfSync dù workload đã Ready. Chỉ prune ConfigMap đã kiểm tra không còn
được workload/Job dùng; không bật prune toàn bộ để xóa PVC, Secret hoặc archive.

## 8. Kết quả kiểm chứng trên cụm đang có

Đã kiểm bằng trình duyệt đăng nhập OIDC thật và API qua Business facade:

- Processing history trả200, có records thật và coverage COMPLETE.
- Trang tiếp theo giữ cùng snapshot và không trùng result IDs.
- Biểu đồ risk trả200, có buckets và markers.
- Thiếu token trả401; máy ngoài phạm vi token trả403.
- Business UI hiển thị bảng lịch sử Processing với khoảng thời gian được chọn.
- CSV nhỏ trả200 và bytes CSV thật.
- Parquet chạy qua job202 -> SUCCEEDED -> download200, kiểm magic bytes PAR1.

Raw history phải được kiểm lại sau khi archive/catalog backfill bắt kịp. Kết quả
trên là kiểm chứng local trên image đang chạy, không phải benchmark100 máy hoặc
xác nhận HA/production. Không lưu tokens, CSV thật, screenshots runtime hoặc
credentials vào repo; bằng chứng chi tiết nằm trong `local/.local/` gitignored.
