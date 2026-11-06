# Bật M6 History trên local k3d

Ngày 06/11/2026. Business và Processing Read API đã có code M6. Tài liệu này
triển khai cấu hình/credential/grants tại hai repo platform. Hai image API được
dùng lại; riêng Storage Consumer được sửa lỗi EOF cũ và build image mới từ source
63a17fa để raw catalog hoạt động trong luồng live. Không thêm History service hoặc DB riêng.

## Luồng request

Browser -> Business History facade -> Processing Read API -> processing_db.
Raw history đọc catalog và object version đã kiểm từ MinIO. Read API dùng một
login chỉ SELECT dữ liệu nguồn và một login `processing_history_meta` chỉ được
CRUD các bảng metadata trong schema `history_meta`.

Business giữ private RSA signing key. Processing chỉ lấy public JWKS qua local
adapter; JWT delegation sống tối đa 60 giây, có actor/machine scope và `azp` khớp
subject thật của service token Keycloak. Hai API có cursor keys độc lập.

Ví dụ, khi người dùng mở lịch sử máy M-001, Business kiểm tra token đăng nhập,
sau đó ký delegation cho đúng người dùng và đúng phạm vi máy. Read API kiểm tra
cả danh tính service Business lẫn delegation này trước khi đọc dữ liệu.

| Cấu hình mới | Vì sao cần |
| --- | --- |
| Private RSA key tại Business | Ký thông tin người đang yêu cầu lịch sử; không thay khóa đăng nhập Keycloak |
| Public JWKS cho Read API | Kiểm chữ ký của Business mà không cần giữ private key |
| Cursor keys riêng từng API | Bảo vệ cursor phân trang, ngăn sửa nội dung hoặc dùng sai phạm vi |
| Login source chỉ SELECT | Đọc readings, prediction và kết quả xử lý trong Processing DB |
| Login metadata CRUD | Lưu snapshot thành viên trang, tiến độ catalog và trạng thái export; không ghi outcome/inference |
| MinIO user riêng cho History | Đọc đúng object version của raw và tạo/tải export ở prefix được cấp quyền |

Snapshot lưu danh sách bản ghi của lần truy vấn đầu, để chuyển sang trang tiếp
không bị trùng hoặc bỏ sót do dữ liệu mới vừa đến. Metadata này nằm trong cùng
Processing DB, ở schema riêng; không thêm một database hoặc service History.

## 1. Chuẩn bị khóa và subject

Tại root infrastructure, sau khi Keycloak local sẵn sàng:

```bash
.venv/bin/python -m pip install -r local/requirements.lock
.venv/bin/python -m localdev.history prepare
.venv/bin/python -m localdev.history seed
```

`prepare` tạo một lần RSA 3072 bit và hai cursor keys 32 byte tại
`local/.local/secrets/history.json`, mode 0600. Chạy lại giữ khóa. Nó lấy service
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
JWKS nằm ở adapter có sẵn của Business, port 18091 nội bộ; Read API gọi qua proxy
loopback, phù hợp guard của local-test. MinIO cũng được nối qua loopback của Read API.
Hai API chỉ đổi adapter. Riêng Storage cần image sửa lỗi audit như mục 9 bên dưới.

`PROCESSING_RETENTION_ENABLED=false` và `PROCESSING_CLEANER_DRY_RUN=true` được giữ
rõ ràng. Bật History không cho phép xóa dữ liệu nguồn.

## 4. Kiểm tra sau rollout

1. Hai Deployment Ready; ESO M6 báo SecretSynced.
2. Trong Business UI, chọn máy -> Lịch sử; chọn khoảng thời gian có dữ liệu.
3. Predictions trả 200 và có records; Sensor readings có raw/catalog coverage.
4. Timeseries/charts trả 200; kiểm cursor trang tiếp không trùng membership.
5. CSV nhỏ trả file thật. Export lớn/Parquet cần job/artifact đã SUCCEEDED.
6. Thiếu auth vẫn 401, sai scope vẫn 403; không dùng token browser gọi trực tiếp Read API.

Nếu raw trả 503, kiểm tuổi/coverage của Storage catalog, quyền MinIO và đồng bộ
catalog metadata. Không bỏ checksum hoặc thay unavailable bằng danh sách rỗng.
Nếu History trả 401, kiểm delegation issuer, kid/JWKS và service subject trước.

## Vận hành khóa

Giữ `history.json` qua restart và chia sẻ đúng Secret giữa replicas cùng API.
Khóa ký khác cursor keys; hai API cũng không dùng chung cursor secret. Runbook
này giữ nguyên khóa qua restart và không tự rotate khóa. Đổi Secret không tự
làm process nạp lại khóa; thay khóa cần một kế hoạch rotation riêng.

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

`archive_replicas` trong selector cho phép từ 1 đến 3 replica local; lần phục hồi
này dùng 3 để xử lý backlog. Tất cả cùng nhóm theo vai trò, nên Kafka phân chia
partition giữa các replica. Catalog dùng CAS để publisher cũ không làm lùi frontier.
Không tăng partition hoặc đổi key máy. Sau khi backfill đạt COMPLETE, selector
đã được đưa về 1 replica để chạy demo thường ngày. Khi đổi số replica, review/push
selector và chạy lại generator thay vì scale tay ngoài GitOps.

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

Read API chỉ cho raw history hoạt động khi đủ 12 partition accepted có coverage
`COMPLETE`, không có gap và generation còn mới trong 120 giây. Trong lúc backfill,
503 raw history là trạng thái chưa sẵn sàng; không đổi thành 200 với danh sách rỗng
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

- Processing history trả 200, có records thật và coverage COMPLETE.
- Trang tiếp theo giữ cùng snapshot và không trùng result IDs.
- Biểu đồ risk trả 200, có buckets và markers.
- Thiếu token trả 401; máy ngoài phạm vi token trả 403.
- Business UI hiển thị bảng lịch sử Processing với khoảng thời gian được chọn.
- CSV nhỏ trả 200 và bytes CSV thật.
- Parquet chạy qua job 202 -> SUCCEEDED -> download 200, kiểm magic bytes PAR1.

Raw history và biểu đồ torque đã trả 200/COMPLETE sau bản sửa EOF; hai bảng
Processing/raw đã hiển thị trên UI thật. Cửa sổ kiểm chứng cuối là 1 phút; CSV
trả 200, Parquet job SUCCEEDED rồi download 200. Sensor vẫn gửi dữ liệu trong
lượt kiểm chứng. Kết quả này là kiểm chứng local, không phải benchmark 100 máy hoặc
xác nhận HA/production. Không lưu tokens, CSV thật, screenshots runtime hoặc
credentials vào repo; bằng chứng chi tiết nằm trong `local/.local/` gitignored.

### Tắt hoặc rollback M6

Lệnh renderer riêng dùng để bật/tái sinh M6 đã bật. Nếu cần tắt, revert bộ commit
cấu hình đã review hoặc chuyển Argo về revision trước khi bật, rồi kiểm tra env
thực trong hai Deployment. Chỉ đổi `enabled=false` trong selector và gọi scoped
renderer không tự gỡ các flags/mounts đã có trong manifest cũ. Giữ metadata, khóa
và bucket trong lần rollback; tắt API không phải quyết định xóa lịch sử.


## 9. Lỗi audit EOF phát hiện khi kiểm tra luồng live

Sau khi archive đã bắt kịp, catalog vẫn có thể báo LAGGING. Một client Kafka giữ
được thông báo PARTITION_EOF từ fetch trước. Ở lượt sau, watermark đã tăng nhưng
code cũ dừng ngay khi đọc EOF cũ, chưa đọc các record mới đã tồn tại. Read API từ
chối raw history theo coverage là đúng; nguyên nhân nằm ở audit chưa đi tới mốc mới.

App PR #40 (`fix/m6-catalog-live-history`, source 63a17fa) sửa đúng điều kiện này:
chỉ dừng tại EOF khi position đã đạt watermark được chụp; nếu chưa thì tiếp tục
poll trong deadline đã có. Trường hợp không có record mới vẫn giữ frontier cũ,
không tự khai COMPLETE, không commit offset của audit và không bỏ kiểm checksum.
Hai regression tests kiểm cả trường hợp có và chưa có record sau EOF cũ.

Image đã build từ source sạch, import vào k3d và chọn bằng receipt riêng của
Storage trong `environments/local/apps/release.json`. GitOps ghi source SHA,
snapshot SHA và image ID thật. Baseline interface lock vẫn là baseline đã review;
bản vá không đổi Kafka schema, catalog schema hoặc migration. Không dùng việc đổi
source lock toàn bộ app để bỏ qua review riêng của component này.

Budget `STORAGE_CATALOG_POLL_SECONDS=2` cho phép fetch có thời gian hoàn thành;
chỉ tăng budget chưa sửa được điều kiện EOF cũ. Cả bản vá và config đều được ghi
phiên bản. Sau rollout, catalog đủ 12 accepted partitions COMPLETE khi Sensor
vẫn chạy; native index của Read API đã nhập generation đó và UI đọc được raw.

Lượt kiểm chứng: Storage 80 tests pass, 2 opt-in integration tests skip local;
CI app có Kafka/MinIO recovery và container checks pass. Hai platform suites có
28 tests infrastructure và 35 tests GitOps. Xem kết quả CI của PR #40 app, PR #4
infrastructure và PR #6 GitOps theo đúng head commit; không suy production/HA từ
các kết quả local này.
