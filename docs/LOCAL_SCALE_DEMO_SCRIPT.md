# Kịch bản và lời thoại demo scale MaintAI trên local

Phiên bản 1.0 — ngày 07/11/2026. Tài liệu bổ sung cho
[video demo chính](LOCAL_DEMO_VIDEO_SCRIPT.md).

**Trạng thái bằng chứng:** đã đối chiếu cấu hình GitOps và code scheduler; chưa
chạy tạo tải hoặc xác nhận autoscale trong lượt bổ sung tài liệu này. Lần đọc
HPA live không kết nối được cụm local. Các mức tải/thời gian dưới đây là kế hoạch
rehearsal, không phải kết quả benchmark đã đạt.

Nên chọn một trong hai cảnh để ghép vào video chính:

| Cảnh | Mục tiêu | Thời gian lên hình | Thời gian rehearsal thực tế |
| --- | --- | --- | --- |
| A — HPA Business API | Tải HTTP tăng → CPU tăng → HPA thêm Pod → giảm tải và quan sát thu nhỏ | 5–7 phút | Khoảng 10–20 phút, gồm chờ ổn định và scale-down |
| B — Processing/Kafka | Tăng readings, quan sát consumer lag, phân phối lại partition và tác động của số worker | 5–7 phút | Khoảng 15–25 phút tùy backlog và giới hạn laptop |

Nếu quay cả A và B, thêm khoảng 10–14 phút vào bản quay chính. Đoạn chờ có thể
cắt hoặc tua nhanh với chú thích; giữ số liệu trước/sau và thời điểm thao tác.

Nếu chỉ chọn một cảnh gắn với luồng cảm biến của đề tài, ưu tiên B. Cảnh A giúp
tách riêng đường đọc HTTP để giải thích HPA dễ hơn; nó không thay cho kiểm thử
tải của toàn pipeline.

## 1. Hiện repo có cơ chế scale nào?

Nguồn: `MaintAI-gitops/environments/local/apps/hpa.yaml`.

| Workload | Min | Max | Metric HPA hiện tại |
| --- | --- | --- | --- |
| Business API | 1 | 4 | CPU utilization 70% |
| Ingestion API | 1 | 4 | CPU utilization 70% |
| Processing Worker | 1 | 4 | CPU utilization 70% |
| ML inference chính | 1 | 4 | CPU utilization 70% |
| Frontend | 1 | 4 | CPU utilization 70% |
| ML shadow | 1 | 2 | CPU utilization 80% |
| RAG | 1 | 3 | CPU utilization 75% |

Các HPA này dùng **CPU**, chưa dùng Kafka lag làm metric kích hoạt. Kafka lag
là số đo để đánh giá pipeline trong cảnh B; chưa có cơ sở nói “Kafka thấy lag
nên tự thêm worker” với cấu hình này.

Business API/Processing Worker hiện có request CPU 100m cho container chính và
25m cho adapter. Metric Resource CPU tính trên Pod, nên mốc 70% tương ứng khoảng
87,5m trung bình/Pod ở cấu hình này; đây không phải 70% của toàn bộ CPU laptop.
CPU sử dụng có thể vượt CPU request, nên utilization có thể lớn hơn 100%.
Quy tắc này được mô tả trong [tài liệu HPA Kubernetes v1.35](https://v1-35.docs.kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/#support-for-resource-metrics).

Ví dụ tính để giải thích, không phải số đo của MaintAI:

```text
desired replicas ≈ ceil(current replicas × CPU utilization / target utilization)
1 Pod × 140% / 70% → đề xuất khoảng 2 Pods
```

Kết quả thật còn phụ thuộc metric thiếu, readiness, tolerance, giới hạn min/max
và chính sách ổn định. HPA có vòng điều khiển mặc định khoảng 15 giây; không hứa
Pod xuất hiện ngay sau một request. Scale-down mặc định có cửa sổ ổn định 5 phút,
không phải cứ dừng tải là số Pod giảm ngay. Xem [thuật toán HPA v1.35](https://v1-35.docs.kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/#algorithm-details).

## 2. Chuẩn bị chung trước khi quay

### 2.1. Chỉ dùng context local và kiểm tra điều kiện

Tại root infrastructure:

```bash
cd /home/chienqt/Dev/newBTL/Maint-infrastructure
k() {
  kubectl --kubeconfig "$PWD/local/.local/kubeconfig" \
    --context k3d-maintai-local "$@"
}
k -n argocd get applications
k -n maintai-local get hpa
k -n maintai-local get deployment business-api processing-worker ml-service sensor
k -n maintai-local top pods --containers
```

Chỉ bắt đầu khi Pod nền Ready và metric CPU đọc được. Nếu HPA hiện `<unknown>`,
kiểm tra Metrics Server/requests/điều kiện HPA trước, không quay như một lần
scale thành công. `kubectl describe hpa` cho biết các conditions và events.

Ghi lại baseline: số replica thực tế, giới hạn HPA, CPU, số máy RUNNING, tốc độ
gửi, Kafka lag và tuổi dữ liệu trên Business UI. Nếu workload đã ở maxReplicas,
nó không thể tiếp tục tăng trong giới hạn hiện tại. Không ép về 1 rồi gọi đó là
kết quả HPA tự phản ứng với tải. Chờ baseline phù hợp hoặc dùng cảnh scale chủ
động được ghi rõ ở mục 6.

Với phép so sánh tải, nên chọn scenario Bình thường trước khi lấy baseline rồi
giữ nguyên trong cả lượt thử. Không đồng thời đổi scenario, model, policy và số
người dùng rồi quy mọi thay đổi latency cho replica. Ghi lại các workload nền
đang chạy vì chúng dùng chung CPU/RAM của laptop.

### 2.2. Màn hình nên bố trí

- Terminal 1: HPA của workload đang demo.
- Terminal 2: Pod/replica và trạng thái Ready.
- Terminal 3: bộ tạo tải hoặc Kafka consumer-group describe.
- Browser: Business UI; Grafana là tab phụ để đối chiếu metrics có thật.

Prometheus tại http://127.0.0.1:19090 dùng để thử các query metric gốc ở mục 4.3
khi panel Grafana chưa khớp tên metric.

Dùng hai lệnh watch riêng vì đây là hai loại resource khác nhau:

```bash
# Terminal 1, đã có hàm k():
k -n maintai-local get hpa business-api-hpa --watch
```

```bash
# Terminal 2, đã có hàm k():
k -n maintai-local get pods -l app.kubernetes.io/name=business-api --watch
```

Nhìn cả Pod Ready và Deployment available replicas. HPA đề xuất 3 nhưng chỉ có
1 Pod Ready thì chưa thể kết luận có 3 Pod đang phục vụ tải.

### 2.3. Quyền quản lý số replica

Argo local đã có ignore `/spec/replicas` và `RespectIgnoreDifferences=true` cho
các Deployment có HPA. HPA quản lý số replica; GitOps tiếp tục quản lý image,
env, probes, volumes và bản thân cấu hình HPA.

Không dùng `kubectl scale` để đối đầu với HPA đang hoạt động. Nếu cần tăng sàn
replica để minh họa có chủ đích, đổi `minReplicas` của HPA qua GitOps như mục 6
và đọc đúng lời thoại “người vận hành thay đổi cấu hình”.

## 3. Cảnh A — HPA Business API dưới tải HTTP có xác thực

Cảnh này tạo tải đọc API máy. Nó kiểm tra đường HTTP Business/DB và cơ chế HPA;
không tạo thêm sensor readings, không chứng minh Processing đã xử lý 100 readings/s.

### 3.1. Chuẩn bị công cụ tạo tải ngoài phần ghi hình

Dùng service token của registry agent hiện có. Token được lưu vào file private,
không đặt vào command arguments hoặc quay phần Authorization. Token agent làm
mới token; vòng lặp bên dưới sao chép lại bằng atomic rename mỗi 30 giây.

Ở một terminal riêng, đứng tại infrastructure và đã có `k()`:

```bash
umask 077
install -d -m 700 local/.local/secrets
while true; do
  scale_read_tmp=$(mktemp local/.local/secrets/scale-read.XXXXXX)
  if k -n maintai-local exec deployment/processing-worker -c local-adapter \
      -- cat /tokens/registry.jwt > "$scale_read_tmp" 2>/dev/null \
      && test -s "$scale_read_tmp"; then
    mv "$scale_read_tmp" local/.local/secrets/scale-read.jwt
  else
    rm -f "$scale_read_tmp"
    printf '%s\n' 'Chưa lấy được service token; kiểm tra Worker/IdP trước khi tạo tải.'
  fi
  sleep 30
done
```

Để terminal này chạy trong rehearsal/quay tải; Ctrl+C khi xong. Đây là quyền đọc
registry của service trong local. Không tắt auth hoặc dùng key giả khi gặp 401/403.

Tạo script private bằng đoạn sau. Script chỉ đọc một URL Business cố định, giới
hạn concurrency, có timeout, và in thống kê; không in token hay response body.

```bash
cat > local/.local/scale_read_load.py <<'PY'
import argparse
import collections
import concurrent.futures as futures
import json
import math
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--rps', type=int, required=True)
parser.add_argument('--seconds', type=int, default=120)
parser.add_argument('--workers', type=int, default=10)
args = parser.parse_args()
if not (1 <= args.rps <= 100 and 1 <= args.seconds <= 600 and 1 <= args.workers <= 32):
    parser.error('Use bounded local load: rps1..100, seconds1..600, workers1..32')
key = Path('local/.local/secrets/scale-read.jwt')
if not key.is_file() or key.stat().st_mode & 0o077:
    raise SystemExit('Prepare the private token file first (mode600).')
url = 'http://127.0.0.1:18080/api/v1/machines?limit=5'
lock = threading.Lock()
auth_failed = threading.Event()
counts = collections.Counter()
latencies = []
skipped = 0
started = time.monotonic()

def request():
    status = 0
    before = time.monotonic()
    try:
        token = key.read_text().strip()
        req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token})
        with urllib.request.urlopen(req, timeout=3) as response:
            response.read(1024 * 1024)
            status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
    except (OSError, urllib.error.URLError):
        pass
    if status in (401, 403):
        auth_failed.set()
    with lock:
        counts[status] += 1
        if status == 200:
            latencies.append((time.monotonic() - before) * 1000)

def report():
    with lock:
        total = sum(counts.values())
        ordered = sorted(latencies)
        p95 = ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)] if ordered else None
        value = {'elapsed_s': round(time.monotonic() - started, 1),
                 'target_rps': args.rps, 'completed': total,
                 'actual_completed_rps': round(total / max(0.001, time.monotonic() - started), 2),
                 'http_200': counts[200], 'errors': total - counts[200],
                 'p95_200_ms': round(p95, 1) if p95 is not None else None,
                 'client_skipped_when_full': skipped}
    print(json.dumps(value), flush=True)

pending = set()
next_request = next_report = started
with futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
    try:
        while time.monotonic() < started + args.seconds and not auth_failed.is_set():
            now = time.monotonic()
            pending = {item for item in pending if not item.done()}
            if now >= next_request:
                if len(pending) < args.workers:
                    pending.add(pool.submit(request))
                else:
                    skipped += 1
                next_request = max(next_request + 1 / args.rps, now)
            if now >= next_report:
                report()
                next_report = now + 10
            time.sleep(0.002)
    except KeyboardInterrupt:
        pass
report()
if auth_failed.is_set():
    raise SystemExit('Stopped: HTTP401/403; fix credentials before continuing.')
PY
```

Lượt HTTP đi qua Business edge → Business API → Business DB, dùng quyền VIEWER
của registry service. Load generator chạy trên host nên không làm CPU của Pod
Worker tăng do chính vòng tạo tải.

`target_rps` là tải muốn phát; `actual_completed_rps` là throughput hoàn tất ở
client. Nếu client đầy hoặc request chậm, số thực tế sẽ thấp hơn mục tiêu.
`p95_200_ms` là latency của request HTTP thành công, chưa phải latency từ Sensor
đến pixel trên trình duyệt. Thống kê lỗi phải được đọc cùng latency.

### 3.2. Các nấc tải để rehearsal

Tại terminal tạo tải, root infrastructure:

```bash
.venv/bin/python local/.local/scale_read_load.py --rps 5 --seconds 120 --workers 10
.venv/bin/python local/.local/scale_read_load.py --rps 15 --seconds 120 --workers 10
.venv/bin/python local/.local/scale_read_load.py --rps 30 --seconds 180 --workers 10
```

Chạy từng nấc, đọc kết quả rồi mới chuyển tiếp. Đây là mức khởi đầu để đo trên
laptop, không hứa 30 rps sẽ tạo đúng 4 replica. Nếu CPU chưa vượt target, dừng ở
kết luận “chưa kích hoạt scale tại mức tải này”; không sửa ngưỡng rồi mô tả như
đã tăng được năng lực pipeline. Nếu lỗi tăng hoặc Pod Pending/OOM, giảm tải.

### 3.3. Timeline và lời thoại quay cảnh A

**Đoạn A1 — Baseline, khoảng 45 giây**

Thao tác: hiện HPA, số Pod Ready, CPU và Business UI. Ghi số thực tế vào bảng
kết quả ở mục 7. Nếu baseline đã max, chọn một lượt rehearsal khác phù hợp.

> Em bắt đầu với tải nền đang có. Business API hiện có [N] Pod Ready. HPA được
> cấu hình từ 1 đến 4 replica và theo dõi CPU với target 70% của CPU request.
>
> Em ghi lại số replica, CPU và thời gian phản hồi trước khi tăng tải để có
> điểm đối chiếu. Các con số tiếp theo sẽ là số đo của lượt chạy local này.

**Đoạn A2 — Tăng tải, khoảng 60–90 giây lên hình**

Thao tác: chạy nấc tải đã rehearsal; giữ terminal HPA và terminal Pod bên cạnh.
Ghi rõ trên video nếu đã cắt đoạn chờ. Mỗi nấc chạy thật theo thời lượng đã chọn.

> Em tăng số request đọc danh sách máy. Các request vẫn có token hợp lệ và đi
> qua Business API như một đường truy cập có xác thực.
>
> CPU trung bình đang là [đọc TARGETS], còn target là [đọc target]. Khi metric
> tạo đề xuất tăng replica, HPA cập nhật Deployment. HPA hoạt động theo từng
> vòng lấy metric, nên em chờ quan sát quyết định thực tế cùng trạng thái Pod.

**Đoạn A3 — Pod mới Ready và phục vụ tải, khoảng 60 giây**

Thao tác: chỉ vào Pod mới Pending → Running → Ready, Deployment available,
thống kê HTTP ở cùng mức tải. Chỉ đọc thay đổi đã xảy ra.

> HPA đã đề xuất [N] replica. Pod mới đang khởi động; khi Pod Ready và được đưa
> vào endpoint phục vụ, nó mới đóng góp năng lực xử lý request.
>
> Ở cùng mức tải này, throughput hoàn tất là [R] request/giây, p95 của request
> thành công là [L] mili giây và có [E] lỗi. Em dùng cả ba số này để đánh giá;
> chỉ thấy số Pod tăng chưa đủ kết luận service nhanh hơn.
>
> Các kết nối mới có thể được phân phối tới Pod Ready. Kết nối SSE đang mở có
> thể vẫn ở Pod cũ; việc tăng replica không có nghĩa phải chuyển mọi kết nối
> đang tồn tại sang một Pod khác ngay lập tức.

Nếu p95 không giảm, đọc: “Replica đã tăng nhưng latency chưa cải thiện rõ ở mức
tải này. Em kiểm tra tiếp DB, edge và tài nguyên node trước khi kết luận.”

**Đoạn A4 — Giảm tải và scale-down, khoảng 60–90 giây lên hình**

Thao tác: dừng script bằng Ctrl+C hoặc chờ hết thời lượng; giữ Sensor nền chạy.
Chờ HPA ổn định, có thể mất hơn 5 phút. Dựng video được tua nhanh có chú thích.

> Em dừng tải bổ sung, giữ lại luồng sensor nền. CPU sẽ được đo lại theo các
> vòng HPA. Số replica không nhất thiết giảm ngay vì có cơ chế ổn định scale-down.
>
> Sau [thời gian thực tế], replica đang là [N]. Nếu tải nền vẫn cần nhiều Pod,
> HPA có thể giữ số đó cao hơn minReplicas. Mức tối thiểu là một giới hạn cấu
> hình, không phải cam kết cứ dừng một tool là service phải về đúng 1 Pod.

Nếu chưa giảm trong thời gian quay, kết thúc bằng trạng thái thực; có thể bổ
sung clip sau khi quan sát. Không dùng scale tay để tạo cảnh “HPA tự thu nhỏ”.

## 4. Cảnh B — Tăng readings và quan sát Processing/Kafka

### 4.1. Tạo tải bằng simulator hiện có

Giữ `SIM_MACHINE_COUNT=5`, dataset, seed, scenario files và state volume hiện có.
Đổi `SIM_SPEED` qua GitOps. Code hiện tại tính nhịp mục tiêu mỗi máy bằng
`SIM_INTERVAL_MS / 1000 / SIM_SPEED`; speed không nằm trong source-identity hash.
Như vậy có thể đổi tốc độ mà không thay identity của dataset/machine inventory.

| SIM_SPEED | Máy RUNNING | Mục tiêu mỗi máy | Mục tiêu tổng |
| --- | --- | --- | --- |
| 1 | 5 | 1 reading/s | 5 readings/s |
| 2 | 5 | 2 readings/s | 10 readings/s |
| 5 | 5 | 5 readings/s | 25 readings/s |
| 10 | 5 | 10 readings/s | 50 readings/s |
| 20, chỉ sau khi đã đo | 5 | 20 readings/s | 100 readings/s |

Đây là tốc độ mong muốn. Scheduler có tick 20 ms, giới hạn sender và durable spool;
HTTP, disk và downstream có thể làm tốc độ sinh/gửi thực tế thấp hơn. Không đọc
hàng cuối thành “đã test 100 máy”: 5 máy × 20 readings/s vẫn là 5 machine keys.

UI Control hiện chưa có API thay rate hoặc số máy. Không mở thêm một replay
process phát đồng thời cùng machine IDs để tạo tải; giữ một Sensor controller
trên SQLite/PVC hiện có. Sensor Deployment dùng Recreate, không scale nó lên
nhiều replica cùng ghi một journal.

### 4.2. Đổi tốc độ có version qua GitOps

Trước hết kiểm tra working tree sạch và Argo đang theo đúng branch/commit sẽ
được push. Chỉ thực hiện các lệnh này khi chạy rehearsal, không phải bước đã được
thực hiện trong lần viết tài liệu ngày 07/11.

```bash
# Tại infrastructure:
k -n argocd get application maintai-local-apps \
  -o jsonpath='{.spec.source.targetRevision}{"\n"}'
cd ../MaintAI-gitops
git status --short --branch
```

Ví dụ nấc 25 readings/s, chỉ sửa đúng config generator Sensor:

```bash
../Maint-infrastructure/.venv/bin/python - <<'PY'
from pathlib import Path
import re
import yaml
p = Path('environments/local/apps/kustomization.yaml')
text = p.read_text()
d = yaml.safe_load(text)
sensor = next(x for x in d['configMapGenerator'] if x['name'] == 'sensor-config')
env = dict(row.split('=', 1) for row in sensor['literals'])
assert env['SIM_MACHINE_COUNT'] == '5' and env['SIM_INTERVAL_MS'] == '1000'
old = next((row for row in sensor['literals'] if row.startswith('SIM_SPEED=')), None)
if old is None:
    marker = '  - SIM_INTERVAL_MS=1000\n'
    assert text.count(marker) == 1
    updated = text.replace(marker, marker + '  - SIM_SPEED=5\n', 1)
    sensor['literals'].insert(sensor['literals'].index('SIM_INTERVAL_MS=1000') + 1,
                              'SIM_SPEED=5')
else:
    pattern = r'(?m)^  - ' + re.escape(old) + r'$'
    updated, count = re.subn(pattern, '  - SIM_SPEED=5', text)
    assert count == 1
    sensor['literals'][sensor['literals'].index(old)] = 'SIM_SPEED=5'
assert yaml.safe_load(updated) == d, 'Unexpected configuration change'
p.write_text(updated)
PY
git diff -- environments/local/apps/kustomization.yaml
```

Review diff, commit rồi push vào revision mà Argo đang theo dõi. Ví dụ khi đang
đứng đúng tracking branch đã được chọn cho demo:

```bash
git add environments/local/apps/kustomization.yaml
git commit -m 'demo(local): raise simulator target to 25 readings per second'
git push
```

Đợi Argo sync và Sensor Ready, rồi mới đo. Cấu hình này rollout lại Sensor nên
có khoảng gián đoạn khởi động. State/cursor/sequence được giữ trên PVC; process
mới có thể tạo stream_epoch mới. Không so sánh thứ tự bằng cách sắp xếp UUID epoch.
Đọc event/sequence trong đúng stream và kiểm tra trạng thái UI theo quy tắc nguồn.

Không đổi `SIM_MACHINE_COUNT` lên 100 trên journal này: số máy nằm trong identity,
code sẽ yêu cầu migration hoặc state volume mới. Test 100 máy cần riêng registry,
IdP machine scope, simulator state và ngân sách hạ tầng được chuẩn bị đồng bộ.

### 4.3. Số đo phải mở khi quay

HPA/Pod của Processing và ML:

```bash
k -n maintai-local get hpa processing-worker-hpa ml-service-hpa
k -n maintai-local get pods -l app.kubernetes.io/name=processing-worker
k -n maintai-local top pods --containers
```

Kafka lag và assignment thật, chạy trước/sau mỗi nấc và sau khi Pod mới Ready:

```bash
k -n maintai-local exec kafka-0 -- \
  /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server kafka:9092 \
  --group local-processing-v1 --describe
```

Không dùng lệnh reset offsets. `--describe` đọc trạng thái group; cột CURRENT-OFFSET,
LOG-END-OFFSET, LAG và CONSUMER-ID giúp đối chiếu tiến độ/assignment từng partition.
Partition rỗng hoặc chưa có committed offset có thể hiện `-`; đừng biến nó thành
một phép đo lag bằng 0 tự đặt.

Metrics có tên thật trong source Sensor/Worker có thể truy vấn ở Prometheus:

```promql
rate(maintai_simulator_generated_total[1m])
maintai_simulator_spool_pending_count
sum(rate(maintai_processing_durable_receipts_total[1m]))
maintai_processing_outbox_pending
```

Rate durable receipts có thể gồm redelivery; không mặc định coi nó bằng số event
nghiệp vụ duy nhất. So sánh cùng thời gian, source IDs và loại counter.

Một số panel Pipeline hiện dùng tên metric khác source và có `or vector(0)`.
Số 0 fallback không chứng minh queue thật bằng 0 hoặc exporter đang hoạt động.
Dùng query metric gốc và Kafka CLI ở trên trước khi chọn panel đưa vào video.

Trên Business UI, xem cả tuổi telemetry, tuổi prediction và Latest Processing.
UI không phải render mọi record trung gian để chứng minh dữ liệu đã xử lý đầy đủ.
Muốn kết luận độ trễ đến trình duyệt cần phép đo theo cùng source event; không
lấy p95 của HTTP list ở cảnh A làm latency của toàn pipeline.

### 4.4. Lời thoại quay cảnh B, khoảng 5–7 phút

**B1 — Giải thích tải và baseline, khoảng 45 giây**

> Lần này em tăng tốc phát readings để quan sát đường xử lý dữ liệu. Em vẫn giữ
> 5 máy giả lập. Ở speed 5, mục tiêu là mỗi máy gửi 5 readings/giây, tổng 25 readings/giây.
> Tốc độ thực tế sẽ được đọc từ counter và tiến độ xử lý, vì scheduler và sender
> vẫn chịu giới hạn của laptop.
>
> Em ghi lại số worker, Kafka lag và tuổi prediction trước khi đổi mức tải.

**B2 — Theo dõi HPA và partition khi worker tăng, khoảng 90 giây**

> HPA của Processing hiện theo CPU. Kafka lag giúp em biết consumer đang bắt kịp
> hay bị chậm, nhưng chưa phải metric trực tiếp làm HPA tăng worker trong cấu hình này.
>
> Khi có thêm worker cùng consumer group, Kafka phân phối lại các partition cho
> các thành viên. Em nhìn CONSUMER-ID và trạng thái Pod Ready để xác nhận worker
> mới đã thực sự nhận việc. Trong lúc rebalance có thể có một đoạn tạm chậm.
>
> Cùng một partition tại một thời điểm thuộc về một consumer trong group này.
> Reading cùng máy được phân vùng theo machine_id, còn worker có bộ điều phối
> xử lý giữa các máy và giữ thứ tự, durability, offset theo thiết kế của Processing.

Nếu HPA không tăng, nói đúng: “Ở mức tải này HPA chưa đề xuất thêm worker”, rồi
phân tích metric. Muốn vẫn minh họa rebalance, chuyển sang nhánh scale chủ động ở
mục 6, gắn nhãn rõ trong video.

**B3 — Đánh giá sau scale, khoảng 90 giây**

> Sau khi worker mới Ready, em giữ nguyên mức tải để so sánh. Lag hiện là [đọc
> các partition liên quan], tuổi prediction khoảng [đọc số thực tế] và có [số]
> lỗi/failed processing được quan sát trong khoảng này.
>
> Nếu năng lực xử lý đang lớn hơn đầu vào, backlog có thể giảm. Nếu lag vẫn tăng,
> cần kiểm tra ML inference, kết nối DB, outbox, phân bố partition hoặc tài nguyên
> node. Thêm worker không tự làm các phụ thuộc đó nhanh hơn.
>
> Topic đang có 12 partition. Đây là giới hạn phân chia assignment của group,
> không phải yêu cầu phải chạy 12 worker. Với 5 machine keys, một số partition có
> thể rỗng và tải cũng có thể lệch. Vì vậy em xem từng partition và từng Pod,
> thay vì mặc định các replica đều có lượng công việc bằng nhau.

**B4 — Giảm tải, drain backlog và khôi phục, khoảng 60–90 giây**

> Em đưa tốc độ simulator về mức nền. Các reading đã được nhận vẫn tiếp tục được
> xử lý; em không xóa queue hay reset offset để đưa lag về 0.
>
> Sau khi backlog bắt kịp, HPA đánh giá lại tải và có thể giảm số replica sau
> cửa sổ ổn định. Em kết thúc bằng trạng thái replica, lag và độ mới dữ liệu
> đang thấy thực tế trên hệ thống.

## 5. Cách kết luận “scale-ready” trong video

> Thiết kế cho phép tăng riêng số replica ở một số thành phần mà không phải
> triển khai lại toàn bộ hệ thống. Consumer group, thứ tự theo máy, outbox/inbox
> và trạng thái bền vững là các cơ chế hỗ trợ việc tăng hoặc giảm số tiến trình.
>
> Cụm k3d này dùng một node trên laptop. Tăng số Pod vẫn dùng tài nguyên của node
> đó; demo chưa chứng minh khả năng chịu lỗi nhiều node hoặc tự cấp thêm máy chủ.
>
> Mốc thiết kế 100 máy cần được kiểm bằng 100 machine IDs thật trong simulator,
> đúng tần suất gửi và workload UI tương ứng. Với x lớn hơn 100, nhóm sẽ đo tải
> x nhân readings/giây/máy, consumer lag, ML/DB, độ trễ và phân bố key để chọn
> replica, concurrency và hạ tầng. Các số đo của video này chỉ áp dụng cho cấu hình
> và mức tải vừa chạy.

Không suy ra năng lực tuyến tính kiểu “1 Pod xử lý 25 thì 4 Pods chắc chắn xử lý 100”.
Cần có số đo ở cùng payload/model/policy, dependencies, thời lượng và error budget.

### 5.1. Nếu cần quay đúng bài toán 100 máy

Đây là lượt kiểm thử riêng sau khi chuẩn bị inventory, không ghép số đo của
5 máy gửi nhanh thành kết quả của 100 máy:

1. Chuẩn bị danh sách 100 machine IDs thống nhất giữa registry, simulator và
   quyền `machine_ids` của các credential cần dùng. Kiểm tra người xem được cấp
   đúng phạm vi; không bỏ kiểm tra quyền để các máy mới xuất hiện.
2. Chuẩn bị migration hoặc state volume riêng cho inventory 100 máy theo guard
   source identity. Giữ state/bucket của demo 5 máy để có thể quay lại; không
   cho hai simulator phát đồng thời cùng machine IDs/stream đang hoạt động.
3. Chọn mục tiêu mỗi máy 1 reading/giây: tổng tải mục tiêu là 100 readings/giây.
   Ghi rõ model, policy, số partition, concurrency, HPA và cấu hình laptop của
   lượt thử; đo tốc độ sinh/gửi thực trước khi đánh giá downstream.
4. Tăng số máy RUNNING theo nấc, chẳng hạn 20 → 50 → 100, qua công cụ điều khiển
   đã hỗ trợ inventory đó. Mỗi nấc giữ đủ lâu để xem lag/độ trễ có tiếp tục tăng
   hay đã ổn định. Không chỉ quay vài giây đầu rồi kết luận đủ capacity.
5. Tại nấc 100 máy, giữ nguyên tải khi quan sát scale, đồng thời ghi lỗi,
   Pod Ready, lag theo partition, ML/DB và độ mới dữ liệu UI. Quay thêm giai đoạn
   hạ tải để kiểm tra backlog được xử lý nốt và HPA ổn định.

Các bước chuẩn bị inventory/state này chưa được thực hiện trong lượt viết
kịch bản. Tài liệu này không cung cấp một lệnh đổi `SIM_MACHINE_COUNT` trên
journal hiện tại như thể đó là thao tác an toàn đã hoàn tất.

**Lời thoại trước lượt thử 100 máy, chỉ dùng sau khi đã chuẩn bị đúng inventory:**

> Lượt này có 100 máy giả lập với 100 định danh riêng. Mỗi máy đặt mục tiêu gửi
> một reading mỗi giây. Em kiểm tra tốc độ thực trước, sau đó quan sát khả năng
> bắt kịp của Processing, inference và phần cập nhật UI.
>
> Kết quả đạt hay chưa phụ thuộc số liệu ở tải này: lag có tăng liên tục không,
> tỷ lệ lỗi là bao nhiêu và dữ liệu lên UI chậm bao lâu. Số replica tăng chỉ là
> một phần của phép kiểm tra.

**Nếu mới quay được 5 máy gửi nhanh và được hỏi về 100 máy:**

> Video hiện chứng minh luồng scale với 5 định danh máy và tốc độ phát cao hơn.
> Mốc 100 máy là giả định thiết kế, cần lượt thử với đủ 100 định danh. Nhóm em
> chưa dùng kết quả 5 máy để khẳng định đã đạt mốc đó.

## 6. Nhánh dự phòng minh bạch — scale chủ động qua GitOps

Dùng khi cần minh họa thêm worker/rebalance nhưng tải rehearsal chưa làm HPA tăng,
hoặc muốn cho thấy người vận hành có thể chọn mức dự phòng. Đây là **manual capacity
change qua GitOps**, không phải bằng chứng CPU đã kích hoạt autoscaling.

Tại repo GitOps, sửa đúng HPA của Processing, giữ max 4 và CPU target hiện có:

```bash
../Maint-infrastructure/.venv/bin/python - <<'PY'
from pathlib import Path
import re
import yaml
p = Path('environments/local/apps/hpa.yaml')
text = p.read_text()
blocks = text.split('\n---\n')
index = next(i for i, block in enumerate(blocks)
             if yaml.safe_load(block)['metadata']['name'] == 'processing-worker-hpa')
hpa = yaml.safe_load(blocks[index])
assert hpa['spec']['maxReplicas'] == 4
hpa['spec']['minReplicas'] = 3
updated, count = re.subn(r'(?m)^  minReplicas: [0-9]+$', '  minReplicas: 3', blocks[index])
assert count == 1 and yaml.safe_load(updated) == hpa
blocks[index] = updated
p.write_text('\n---\n'.join(blocks))
PY
git diff -- environments/local/apps/hpa.yaml
```

Review/commit/push vào revision Argo đang theo dõi, rồi đợi HPA và Pod Ready.
Nếu ban đầu đã có 3 hoặc 4 worker thì đổi sàn lên 3 không làm xuất hiện thêm worker;
chỉ quay sự thay đổi replica khi nó thực sự xảy ra. Giữ tải trước/sau giống nhau
nếu muốn đánh giá tác động của số worker.

**Lời thoại:**

> Ở cảnh này em chủ động nâng mức tối thiểu của Processing lên 3 replica trong
> GitOps. Argo đồng bộ HPA, sau đó HPA duy trì sàn đã chọn. Đây là quyết định
> cấu hình của người vận hành.
>
> Em quan sát Pod mới Ready, assignment trong consumer group và lag sau khi giữ
> nguyên tải. Cảnh này minh họa khả năng thay đổi capacity có quản lý phiên bản
> và cách Kafka phân chia lại công việc.

Sau cảnh quay, đưa `minReplicas` về giá trị baseline đã ghi lại, không sửa
Deployment.replicas để ghi đè HPA.

## 7. Bảng số liệu cho người quay điền

Để trống tới khi đã chạy. Số liệu phải có thời gian quan sát; không điền các con
số minh họa trong tài liệu thành kết quả thực nghiệm.

| Giai đoạn | Tải mục tiêu và tải thực | Pod Ready | CPU/HPA target | HTTP p95/error hoặc lag | Tuổi prediction |
| --- | --- | --- | --- | --- | --- |
| Baseline | … | … | … | … | … |
| Tăng tải, trước scale | … | … | … | … | … |
| Cùng tải, sau scale | … | … | … | … | … |
| Hạ tải, đang drain | … | … | … | … | … |
| Ổn định cuối | … | … | … | … | … |

Nếu thay đồng thời tải và replica, ghi cả hai thay đổi. Không kết luận cải thiện
là do riêng scale khi điều kiện so sánh cũng đã đổi.

## 8. Khôi phục sau rehearsal/quay

1. Dừng load HTTP; dừng vòng sao chép token ở terminal riêng. Có thể xóa riêng
   `local/.local/secrets/scale-read.jwt`; giữ các Secrets/credential chuẩn của hệ thống.
2. Đưa `SIM_SPEED` về baseline đã ghi; nếu trước đó không khai báo thì bỏ riêng
   literal SIM_SPEED. Giữ dataset, machine count, state volume và các env khác.
3. Nếu đã đổi sàn HPA, đưa minReplicas về baseline bằng GitOps.
4. Review/commit/push diff; chờ Argo đồng bộ, Pod Ready và backlog xử lý nốt.
5. Kiểm Business UI tiếp tục cập nhật, không có lỗi auth hoặc source identity.

Tăng SIM_SPEED không bắt buộc tăng số máy. Nếu gặp lỗi source identity sau một
thay đổi khác, khôi phục cấu hình đúng trước; không xóa SQLite/PVC để vượt guard.

## 9. Những trường hợp không được đọc lời thoại “scale thành công”

| Hiện tượng | Kết luận và xử lý đúng |
| --- | --- |
| HPA `<unknown>` | Chưa có metric đủ dùng; kiểm Metrics Server/requests và conditions |
| HPA muốn tăng nhưng Pod Pending | Thiếu tài nguyên hoặc scheduling/image/volume chưa thỏa; chưa có thêm capacity Ready |
| Đã chạm max 4 | Giới hạn cấu hình hiện tại đã chặn tăng tiếp; không suy rằng scale không giới hạn |
| Replica tăng nhưng lag/latency không cải thiện | Xác định ML/DB/edge/partition hoặc node trước khi kết luận |
| CPU thấp nhưng lag cao | HPA CPU không giải quyết mọi kiểu chờ I/O; xem dependencies và concurrency |
| HTTP 401/403 khi tạo tải | Credential/scope sai hoặc hết hạn; dừng và sửa auth |
| Grafana hiện 0 do `or vector(0)` | Chưa đủ bằng chứng metric thật bằng 0; kiểm query nguồn/CLI |
| Dừng HTTP load nhưng HPA chưa giảm | Tải nền hoặc cơ chế ổn định còn giữ replica; tiếp tục quan sát |

## 10. Nguồn để đối chiếu

- Cấu hình HPA: `MaintAI-gitops/environments/local/apps/hpa.yaml`.
- Source CPU requests: manifests Business API/Processing Worker dưới `environments/local/apps/generated/`.
- Quyền sở hữu replicas: `Maint-infrastructure/localdev/cli.py`, hàm `local_autoscaling_options()`.
- Nhịp Sensor: `MaintAI/sensor/src/simulator/scheduling/engine.py`, `tick()`.
- Identity/state: `MaintAI/sensor/src/simulator/ordering/store.py` và constructor engine.
- Metrics source: `sensor/src/simulator/metrics.py`, `processing/worker/src/consumer/observability.py`.
- [HPA Kubernetes v1.35](https://v1-35.docs.kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/).

Tài liệu không kích hoạt thay đổi cluster. Chỉ thực hiện các lệnh thay cấu hình
khi chạy rehearsal có chủ đích và giữ lại kết quả đo tương ứng.
