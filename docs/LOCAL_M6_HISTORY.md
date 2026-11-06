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

Policy MinIO chỉ cho đọc raw-sensor/raw-catalog trong `maintai-raw`, và ghi/đọc
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
Lệnh chỉ cập nhật M6 của hai API, giữ các resource Phase2 khác. Generator chuẩn
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
