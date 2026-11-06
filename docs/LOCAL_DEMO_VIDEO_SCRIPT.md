# Kịch bản và lời thoại video demo MaintAI trên local

Phiên bản kịch bản: 1.0 — ngày 06/11/2026. Đối tượng xem: giảng viên đánh giá
đồ án. Người trình bày có thể đọc phần **Lời thoại**; các mục **Thao tác** và
**Kết quả cần thấy** dành cho người quay, không cần đọc lên.

Bản quay chính dài khoảng **13–15 phút**. Nếu quay cả phần RAG API và giới thiệu
MLflow thì dự trù **17–19 phút**. Quay từng cảnh rồi ghép; thời gian chờ dữ liệu
hoặc provider có thể cắt ngắn và chú thích thời gian chờ thực tế.

## 1. Phạm vi thực tế để chọn cảnh quay

Các kết quả dưới đây đã được kiểm tra trên cụm local ngày 06/11:

| Nội dung | Bằng chứng dùng để quay |
| --- | --- |
| Simulator → Ingestion → Kafka → Processing → ML → Business UI | Telemetry và prediction thật cập nhật qua API/SSE |
| Pause/Resume từng máy | Thử trực tiếp trên Simulator UI: M-001 dừng, M-002 vẫn cập nhật; Resume làm M-001 tiếp tục |
| Scenario Critical | Đầu vào thay đổi; M-002 đã có kết quả HIGH, xác suất lỗi cao nhất khoảng 0,743 trong lượt thử |
| History Processing và raw | API trả 200, coverage COMPLETE; cả hai bảng xuất hiện trên Business UI |
| Phân trang và biểu đồ | Cùng snapshot, không trùng result ID; biểu đồ risk và torque trả dữ liệu |
| Export | CSV tải được; Parquet job SUCCEEDED và tải file hợp lệ |
| Phân quyền History | Không có token trả 401; máy ngoài phạm vi token trả 403 |
| RAG core gọi Groq | Gọi bằng context của alert thật: HTTP 200, GROUNDED, 5 bước checklist và 2 citations trong lượt thử |
| Tích hợp Copilot trên Business UI | **Chưa bật M7 trong cấu hình local; facade hiện trả UNAVAILABLE** |
| Monitoring | Prometheus trả dữ liệu; Grafana là UI upstream đã triển khai |
| MLflow | Server/UI truy cập được; lần kiểm tra có 1 experiment và 0 registered models |

**Chọn cảnh theo bảng này:** đưa History vào bản quay chính. RAG hiện quay bằng
API nội bộ như cảnh 10; không đọc lời thoại rằng nút Copilot trên Business UI đã
hoàn tất tích hợp. MLflow, drift và training không được coi là đã chạy thành công
chỉ vì Deployment, trang UI hoặc dashboard đã tồn tại.

Tên scenario `critical` mô tả cách làm căng đầu vào. Model và risk policy vẫn
quyết định đầu ra. Trong video, đọc đúng HIGH hoặc CRITICAL đang hiển thị; không
nói rằng chọn Critical thì bắt buộc prediction phải là FAILURE/CRITICAL.

## 2. Chuẩn bị trước khi bấm quay

### 2.1. Màn hình và tài khoản

Mở sẵn các tab:

| Tab | Địa chỉ hoặc file |
| --- | --- |
| Business UI | http://127.0.0.1:18080 |
| Simulator UI | http://127.0.0.1:18081 |
| Grafana | http://127.0.0.1:13000 |
| MLflow, nếu quay phần mở rộng | http://127.0.0.1:15000 |
| Sơ đồ kiến trúc | `../MaintAI/docs/diagrams/03-logical-architecture.png` |
| Sơ đồ triển khai, nếu cần | `../MaintAI/docs/diagrams/04-deployment.png` |

Đăng nhập trước bằng tài khoản `administrator` để quay cả xem dữ liệu và điều
khiển simulator. Password nằm trong private state của laptop; không mở file
credential hoặc cửa sổ Secret trong lúc ghi hình. Có thể chuẩn bị thêm một cửa
sổ ẩn danh với tài khoản `viewer` cho cảnh phân quyền tùy chọn.

Dùng zoom khoảng 90–100%, font đủ lớn. Với cảnh đối chiếu thời gian thực, đặt
Simulator và Business UI cạnh nhau. Đóng popup, thông báo và tab không liên quan.

### 2.2. Kiểm tra cụm bằng terminal riêng

Đứng tại root `Maint-infrastructure` rồi tạo hàm chỉ dùng kubeconfig local:

```bash
cd /home/chienqt/Dev/newBTL/Maint-infrastructure
k() {
  kubectl --kubeconfig "$PWD/local/.local/kubeconfig" \
    --context k3d-maintai-local "$@"
}
k -n argocd get applications
k -n maintai-local get pods
k -n maintai-local get externalsecrets
```

Trước khi quay: ba Applications phải Synced/Healthy, các Pod cần dùng phải Ready,
các ExternalSecret phải Ready=True. Job Completed là trạng thái bình thường.
Nếu có lỗi, xử lý trước theo `LOCAL_M6_HISTORY.md`; không đọc dòng “hệ thống khỏe”
khi màn hình đang báo lỗi hoặc chưa đồng bộ.

Lần bật M6 đã tạo một archive namespace mới theo Kafka lineage, giữ bucket cũ.
Không reset Kafka offset, xóa DB hoặc xóa bucket để làm sạch màn hình demo.
Dữ liệu thử, alert và audit trong buổi chạy thử được giữ nguyên.

### 2.3. Chuẩn bị dữ liệu cho từng cảnh

- Chọn M-001 làm máy theo dõi chính và kiểm tra Pause/Resume.
- Chọn M-002 làm máy đổi scenario. Máy khác tiếp tục chạy để so sánh.
- Cho hai máy chạy Bình thường một lúc. Ghi nhớ thời điểm bắt đầu để truy vấn History.
- Kiểm tra trước một alert OPEN để quay lifecycle. Với alert cũ, giữ nguyên evidence
  và giải thích đó là snapshot tại thời điểm cảnh báo được mở.
- Trong History, chọn **khoảng 1 phút có dữ liệu**. Khoảng này đã được kiểm tra trên
  laptop. Chưa dùng kết quả đó để khẳng định cửa sổ hàng giờ có cùng độ trễ.
- Chạy thử scenario trước buổi quay để chọn khoảng dữ liệu thực sự có HIGH/CRITICAL.
  Không đổi threshold, trả prediction giả hoặc sửa DB để ép cảnh báo xuất hiện.

`degradation` và `recovery` hiện có ramp **300 readings/máy**. Ở mục tiêu 1
reading/giây/máy, một ramp mất khoảng 5 phút. Bản quay chính dùng Critical để
quan sát phản ứng nhanh; hai ramp dành cho cảnh mở rộng, tua nhanh có chú thích
hoặc quay riêng. Không hứa recovery hoàn tất trong 20–30 giây.

## 3. Timeline bản quay chính

| Mốc dự kiến | Cảnh | Điều cần chứng minh |
| --- | --- | --- |
| 00:00–00:45 | Giới thiệu bài toán | Hệ thống phục vụ ai và giải quyết việc gì |
| 00:45–02:00 | Sơ đồ kiến trúc | Luồng dữ liệu và ranh giới các thành phần |
| 02:00–03:15 | Fleet và chi tiết máy | Ba trục telemetry/prediction/processing |
| 03:15–04:30 | Pause/Resume | Cô lập theo máy, máy khác vẫn chạy |
| 04:30–06:15 | Critical và risk | Dữ liệu đi qua ML/risk thật |
| 06:15–08:30 | Xử lý alert | Evidence, lifecycle, audit và feedback |
| 08:30–11:30 | History và export | Processing/raw, biểu đồ, CSV, Parquet |
| 11:30–13:30 | Grafana và GitOps | Quan sát dịch vụ và trạng thái triển khai |
| 13:30–14:15 | Kết thúc | Những kết quả vừa chứng minh và giới hạn |

Mốc thời gian là phân bổ nội dung, không phải SLA của phần mềm. Nếu phải đợi
model, alert hoặc export thì để phần thao tác chạy thật rồi cắt đoạn chờ khi dựng.

## 4. Cảnh 1 — Giới thiệu, khoảng 45 giây

**Thao tác:** hiện slide tên đề tài hoặc Fleet. Để thông tin nhóm ở một góc màn hình.

**Lời thoại:**

> Em xin chào thầy. Nhóm em là Nhóm 8, thực hiện đề tài MaintAI — hệ thống hỗ trợ
> giám sát máy và bảo trì dựa trên dữ liệu cảm biến.
>
> Trong phần demo này, nhóm em trình bày cách dữ liệu đi từ máy giả lập đến giao
> diện giám sát, cách hệ thống đưa ra prediction và mức rủi ro, cách kỹ thuật viên
> xử lý cảnh báo, và cách tra cứu lại lịch sử của các bản ghi.
>
> Môi trường đang chạy trên laptop bằng Kubernetes k3d và Argo CD. Demo sử dụng
> 5 máy giả lập, với mục tiêu mỗi máy gửi một bản ghi mỗi giây.

Thông tin nhóm để làm slide mở đầu/cuối video:

| MSV | Thành viên |
| --- | --- |
| 24021486 | Nguyễn Công Huy Hoàng |
| 24021482 | Nguyễn Duy Hòa |
| 24021414 | Lại Tuấn Đức |
| 23021490 | Bùi Anh Chiến |

## 5. Cảnh 2 — Giải thích kiến trúc, khoảng 75 giây

**Thao tác:** mở sơ đồ logical architecture. Trỏ chuột lần lượt vào Sensor,
Ingestion, Kafka, Processing/ML, Business và UI; sau đó vào nhánh archive.

**Lời thoại:**

> Sensor Simulator phát dữ liệu vào Ingestion API. API này kiểm tra thông tin
> bao ngoài và quyền gửi, rồi đưa bản ghi vào Kafka.
>
> Processing Worker nhận bản ghi, kiểm tra chất lượng dữ liệu, gọi model suy
> luận và áp dụng risk policy. Kết quả được lưu cùng thông tin nguồn và phiên
> bản. Outbox Relay tiếp tục phát kết quả đã lưu sang Kafka để Business cập nhật
> trạng thái phục vụ giao diện.
>
> Song song với xử lý dự đoán, Storage Consumer lưu dữ liệu gốc vào MinIO và
> công bố catalog có checksum, phiên bản object và coverage. Khi người dùng xem
> lịch sử, trình duyệt vẫn gọi Business API. Business chuyển yêu cầu có phân quyền
> sang Processing Read API để đọc kết quả hoặc raw archive.
>
> Simulator UI được tách riêng khỏi Business UI. Một giao diện dùng để điều
> khiển demo, còn một giao diện dành cho người theo dõi và xử lý công việc bảo trì.

**Lưu ý khi nói:** đây là các máy được gán ID trong simulator. AI4I gốc không
cung cấp một đội máy thật với chuỗi thời gian thật. Dữ liệu đang replay có thêm
machine ID, thời gian và sequence của hệ thống giả lập.

## 6. Cảnh 3 — Fleet và ba panel của máy, khoảng 75 giây

**Thao tác:** vào Business UI → Fleet → `Xem M-001`. Chỉ lần lượt vào Live
Telemetry, Latest Valid Prediction và Latest Processing. Để số liệu thay đổi vài giây.

**Kết quả cần thấy:** telemetry đổi, prediction có source event/model/policy,
processing thể hiện kết quả xử lý gần nhất. Các mốc thời gian có thể khác nhau.

**Lời thoại:**

> Đây là danh sách các máy đang được giám sát. Em mở chi tiết M-001.
>
> Panel đầu là dữ liệu cảm biến mới nhận. Panel thứ hai là prediction hợp lệ gần
> nhất, có thông tin bản ghi nguồn và phiên bản model. Panel thứ ba cho biết bản
> ghi gần nhất đang được xử lý như thế nào.
>
> Ba thông tin này được hiển thị riêng để người dùng biết dữ liệu đã tới đâu.
> Một số đo mới đến chưa có nghĩa model đã xử lý xong số đo đó. Nếu lần xử lý
> mới gặp lỗi, hệ thống vẫn giữ prediction hợp lệ trước đó và hiển thị độ mới
> cùng trạng thái xử lý, để người xem không hiểu nhầm đó là kết quả của bản ghi mới.

## 7. Cảnh 4 — Pause/Resume theo máy, khoảng 75 giây

**Thao tác:** đặt hai cửa sổ cạnh nhau. Simulator chọn M-001 → `Pause`. Giữ một
máy khác như M-002 trong tầm nhìn. Chờ khoảng 10 giây cho phần đang gửi xử lý nốt;
so sánh event/sequence và tuổi dữ liệu. Sau đó bấm `Resume`.

**Kết quả cần thấy:** M-001 ngừng có bản ghi mới sau khi backlog đã hết, M-002 vẫn
cập nhật; Resume làm M-001 tiếp tục. Chỉ kết luận STALE nếu UI thực sự hiện trạng thái đó.

**Lời thoại:**

> Em tạm dừng M-001. Thao tác này dừng tạo bản ghi mới cho riêng máy đó.
> Các bản ghi đã nằm trong hàng đợi vẫn được phép gửi tiếp, nên em chờ xử lý nốt
> phần đang đi trên đường truyền.
>
> Lúc này bản ghi của M-001 đã đứng lại, trong khi M-002 vẫn cập nhật. Điều đó
> cho thấy việc điều khiển một máy không làm dừng toàn bộ simulator hoặc pipeline.
>
> Em tiếp tục M-001. Dữ liệu mới xuất hiện trở lại. Sequence của từng máy được
> duy trì trong trạng thái bền vững, thay vì tạo lại ID tùy ý sau mỗi lần gửi.

## 8. Cảnh 5 — Scenario Critical, prediction và risk, khoảng 105 giây

**Thao tác:** Simulator chọn M-002 → `Kịch bản Critical`. Business mở M-002 và
quan sát thông số, probability, machine state. Đợi kết quả HIGH/CRITICAL đã rehearsal.
Mở danh sách alert, lọc theo M-002 và xem cảnh báo phù hợp với thời điểm đó.

**Lời thoại:**

> Em chuyển M-002 sang kịch bản Critical. Simulator thay đổi đầu vào theo
> kịch bản đã định nghĩa, như tăng torque và giảm tốc độ quay. Bản ghi vẫn phải
> đi qua Ingestion, Kafka, kiểm tra dữ liệu và model thật.
>
> Tại bản ghi đang thấy, model trả xác suất lỗi là [đọc số trên màn hình].
> Risk policy chuyển kết quả này thành mức [đọc HIGH hoặc CRITICAL].
> Khi mức rủi ro thỏa điều kiện, hệ thống phát tín hiệu để Business tạo hoặc xử lý
> cảnh báo theo quy tắc chống trùng.
>
> Tên Critical là tên kịch bản đầu vào. Nó không phải lệnh ép model trả một nhãn
> cố định. Số xác suất trên màn hình cũng không phải độ chính xác của toàn bộ model;
> độ chính xác phải được đánh giá riêng trên tập dữ liệu và quy trình phù hợp.

**Nếu chưa lên HIGH trong thời gian dự kiến:** giữ lời giải thích đầu vào và đợi
đoạn đã rehearsal, hoặc dùng alert thật đã chuẩn bị. Không nói một alert cũ vừa
được tạo trong cảnh này; đối chiếu timestamp và source event trước khi quay.

## 9. Cảnh 6 — Alert lifecycle, evidence và feedback, khoảng 135 giây

**Thao tác:** mở một alert OPEN. Cho thấy snapshot cảm biến, probability,
model/policy version và timeline. Chọn lần lượt:

1. `Tiếp nhận` → ACKNOWLEDGED; ghi chú “Nhận kiểm tra máy trong buổi demo”.
2. `Bắt đầu xử lý` → IN_PROGRESS.
3. Trước khi đóng alert, đưa simulator về Bình thường hoặc quay phần recovery riêng.
4. `Hoàn tất xử lý`; nhập kết quả kiểm tra có ý nghĩa, chẳng hạn
   “Đã kiểm tra thông số mô phỏng và xác nhận hoàn tất kịch bản demo”.
5. Kiểm tra timeline và thử `Gửi feedback` với kết luận phù hợp.

Đây là các thao tác có ghi audit thật. Chỉ dùng alert dành cho demo; không xóa
lịch sử hoặc sửa DB để quay lại trạng thái OPEN.

**Lời thoại:**

> Cảnh báo giữ lại bằng chứng tại thời điểm được tạo: bản ghi nguồn, thông số,
> prediction và phiên bản model, policy. Việc số đo hiện tại đã thay đổi không
> làm thay đổi snapshot gốc của cảnh báo này.
>
> Em tiếp nhận cảnh báo và bắt đầu xử lý. Mỗi thao tác được lưu cùng người thực
> hiện, thời gian và ghi chú trong timeline.
>
> Sau khi hoàn tất kiểm tra, em nhập kết quả và đóng cảnh báo. Việc đưa simulator
> về điều kiện bình thường không tự xác nhận rằng kỹ thuật viên đã xử lý xong.
> Trạng thái công việc và trạng thái dữ liệu được quản lý riêng.
>
> Kỹ thuật viên có thể gửi feedback về kết luận kiểm tra và độ hữu ích của khuyến
> nghị. Nếu chưa có khuyến nghị RAG cho alert này thì chọn NOT_AVAILABLE, không
> đánh giá một khuyến nghị chưa được tạo.

## 10. Cảnh 7 — History, biểu đồ và export, khoảng 3 phút

**Thao tác chính xác:**

1. Business → chi tiết M-001 → `Lịch sử`.
2. Đặt “Từ thời điểm” và “Đến thời điểm” thành **một phút có dữ liệu vừa chạy**.
3. “Nguồn lịch sử” chọn `Kết quả xử lý` → `Áp dụng`.
4. Chỉ vào source event, kết quả và thông tin version; chuyển trang nếu có.
5. Ở biểu đồ, chọn metric `risk_score`, chọn độ phân giải phù hợp rồi áp dụng biểu đồ.
6. Chuyển “Nguồn lịch sử” sang `Dữ liệu cảm biến` → `Áp dụng`.
7. Chỉ vào received_at, sequence, features và trạng thái validation; xem metric `torque_nm`.
8. Xuất CSV từ nguồn muốn minh họa. Nếu dùng raw, giữ khoảng nhỏ đã chạy thử.
9. Chuyển lại `Kết quả xử lý` trước cảnh Parquet để lặp đúng luồng đã kiểm chứng:
   bấm `Tạo Parquet job`, đợi SUCCEEDED, bấm `Tải tệp export`.

**Lời thoại:**

> Ngoài dữ liệu mới nhất, người dùng có thể xem lại lịch sử theo máy và khoảng thời gian.
> Em bắt đầu với kết quả xử lý. Các bản ghi này cho biết hệ thống đã kết luận gì
> và đã dùng phiên bản model, policy nào.
>
> Khi phân trang, hệ thống sử dụng snapshot của truy vấn. Dữ liệu mới tiếp tục
> tới sẽ không làm bản ghi bị nhảy giữa hai trang của cùng snapshot.
>
> Em chuyển sang dữ liệu cảm biến gốc. Nguồn này được đọc qua catalog của MinIO,
> có kiểm tra object version và checksum. Business không để trình duyệt tự truy
> cập bucket hoặc kết nối trực tiếp vào database của Processing.
>
> Biểu đồ giúp quan sát biến động theo thời gian. Với raw history, trục thời gian
> dựa trên received_at; lịch sử xử lý dựa trên thời điểm xử lý hoàn tất. Hai mốc
> này có ý nghĩa khác nhau khi pipeline có độ trễ hoặc đang xử lý backlog.
>
> CSV phục vụ việc tải dữ liệu về phân tích thêm. Với Parquet, yêu cầu tạo một job.
> Giao diện theo dõi trạng thái và chỉ cho tải khi artifact đã hoàn tất.
> Việc xuất file là một chức năng bổ sung; người dùng vẫn xem lịch sử trực tiếp trên UI.

**Cần phân biệt khi quay:** nút “Lịch sử xử lý” trong trang alert là audit thao tác
của alert; tab “Lịch sử” trong chi tiết máy là history readings/prediction.

## 11. Cảnh 8 — Grafana và Argo CD, khoảng 2 phút

**Thao tác:** Grafana chọn dashboard `MaintAI — System Overview & Fleet Health` hoặc
`MaintAI — Pipeline, Kafka & Outbox Relay`,
chọn “Last 15 minutes”, refresh. Chỉ các panel thực sự có dữ liệu. Chuyển terminal
và chạy `k -n argocd get applications`, rồi hiện các Pod cần dùng.

**Lời thoại:**

> Business UI dành cho người theo dõi máy và xử lý bảo trì. Grafana dành cho
> việc quan sát vận hành hệ thống, chẳng hạn tình trạng service và các metrics
> về xử lý dữ liệu hoặc suy luận, tùy panel đang có dữ liệu thực.
>
> Phần triển khai local được quản lý bằng Argo CD. Các Applications đọc cấu
> hình từ GitOps repo. Synced cho biết cấu hình đã đồng bộ; Healthy cho biết các
> resource đạt điều kiện sức khỏe mà Kubernetes và Argo đang theo dõi.
>
> Để xác nhận tính năng, nhóm em vẫn phải kiểm tra luồng trên giao diện như các
> cảnh vừa rồi. Chỉ có Pod Ready hoặc Argo Healthy thì chưa đủ chứng minh
> prediction, alert và history đã đi trọn pipeline.

Không dùng panel No data để kết luận “không có drift”. Nếu Drift Worker chưa
được bật hoặc chưa có report, bỏ cảnh báo cáo drift khỏi bản quay chính.
Không đọc một panel Kafka lag là số liệu thật nếu exporter/series đó chưa có.

## 12. Cảnh 9 — Kết thúc, khoảng 45 giây

**Thao tác:** trở về Business Fleet hoặc slide kiến trúc tổng thể.

**Lời thoại:**

> Phần demo đã cho thấy dữ liệu từ simulator được tiếp nhận, xử lý và hiển thị;
> việc Pause một máy không dừng các máy còn lại; prediction và risk dẫn tới
> cảnh báo có bằng chứng; người dùng xem được lịch sử và tải dữ liệu.
>
> Thiết kế của nhóm lấy mốc 100 máy làm cơ sở tính toán và có ranh giới để tăng
> replica riêng cho từng phần. Lần quay này chạy 5 máy giả lập trên laptop.
> Khi tăng tải, nhóm sẽ đo consumer lag, thời gian xử lý, tải database và độ trễ
> đến giao diện để chọn cấu hình phù hợp, thay vì suy rằng cứ thêm máy là phải
> thêm từng ấy partition hoặc consumer.
>
> Nhóm em xin kết thúc phần demo tại đây. Em cảm ơn thầy.

## 13. Cảnh mở rộng A — RAG core với Groq, khoảng 2–3 phút

Cảnh này hiện **quay API RAG riêng**. Business M7 chưa bật nên không bấm
“Tạo khuyến nghị” rồi mô tả như đã tích hợp thành công trên Business UI.

Lần rehearsal đã tạo private input `local/.local/demo-rag-input.json` từ evidence
của một alert thật trong Business. File không chứa Groq key. Có thể dùng lại cho
cảnh quay hoặc chuẩn bị một context alert khác theo schema
`MaintAI/contracts/v1.3/schemas/brief-request.schema.json`.

Ở terminal đã có hàm `k()` và đứng tại root infrastructure:

```bash
k -n maintai-local exec -i deployment/rag-service -- python -c '
import json, sys, urllib.request
payload = json.load(sys.stdin)
request = urllib.request.Request(
    "http://127.0.0.1:8002/api/v1/briefs",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(request, timeout=75) as response:
    result = json.load(response)
print(json.dumps(result, ensure_ascii=False, indent=2))
' < local/.local/demo-rag-input.json
```

Key được RAG Pod đọc từ Secret; không đưa key vào câu lệnh quay màn hình.
Đây là thao tác của người vận hành có quyền kubectl trong local, không phải
một endpoint công khai để trình duyệt bỏ qua Business auth.

**Lời thoại:**

> Nhóm em kiểm tra thêm phần lõi RAG. Đầu vào là evidence của một cảnh báo:
> thông tin máy, prediction, risk và các thông số liên quan.
>
> Service truy tìm các đoạn tài liệu trong knowledge database, dùng embedding
> để chọn ngữ cảnh, sau đó gọi Groq để sinh checklist. Kết quả đang thấy có trạng
> thái [đọc grounded_status], các bước kiểm tra và nguồn trích dẫn.
>
> Các citations cho phép người dùng mở lại tài liệu, trang hoặc đoạn tham chiếu
> để kiểm tra căn cứ của gợi ý. Phần này hỗ trợ kỹ thuật viên; nó không tự thực
> hiện việc sửa máy hoặc tự đóng cảnh báo.
>
> Ở cấu hình local của lần quay này, nhóm em đang minh họa API lõi. Việc bật
> điều phối Copilot trên Business UI là phần cấu hình tích hợp M7 riêng.

Chỉ đọc “GROUNDED” và số citations khi response thật có các trường đó. Lượt thử
ngày 06/11 trả 200/GROUNDED, 5 bước và 2 citations trong khoảng 8,3 giây; lần quay
khác có thể có thời gian/nội dung khác. Nếu provider unavailable, giữ đúng phản
hồi lỗi; không dùng response mẫu rồi mô tả là kết quả live.

## 14. Cảnh mở rộng B — MLflow, khoảng 30–45 giây

**Thao tác:** mở http://127.0.0.1:15000. Nếu chưa có run/model, chỉ giới thiệu vai
trò của UI hoặc bỏ cảnh để video gọn hơn.

**Lời thoại dùng khi chưa có registered model:**

> Đây là giao diện có sẵn của MLflow Server để theo dõi experiment và quản lý
> model registry khi pipeline training ghi dữ liệu vào đó. Ở lần kiểm tra local
> này chưa có registered model, nên nhóm em không trình bày một quá trình promote
> model đã hoàn tất. Model phục vụ inference trong demo được nạp từ bundle đã chuẩn bị.

Không đồng nhất MLflow Server đã chạy với training/registry đã có dữ liệu.
Không gọi shadow Deployment là một promotion thành công chỉ vì cả hai Pod Ready.

## 15. Cảnh mở rộng C — Suy giảm và hồi phục

Nếu cần thể hiện đủ bốn scenario của UI:

- Quay Suy giảm thành một cảnh riêng dài khoảng 5 phút hoặc tua nhanh có nhãn tốc độ.
  Quan sát feature đổi dần; đọc prediction thực tế, không gán nhãn lỗi chỉ từ tên scenario.
- Quay Hồi phục theo cùng cách. Đưa torque/tốc độ về dần vùng nền không đồng nghĩa
  một máy vật lý đã được sửa xong, vì đây là simulator replay dữ liệu.
- Cho thấy alert đang mở vẫn có lifecycle riêng. Chỉ người có quyền thực hiện thao
  tác hoàn tất mới chuyển trạng thái công việc.

**Lời thoại ngắn:**

> Kịch bản Suy giảm thay đổi đầu vào dần theo số bản ghi của máy. Kịch bản Hồi
> phục đưa đầu vào dần về vùng nền. Hai cảnh này cho phép quan sát phản ứng của
> pipeline theo một quá trình, thay vì chỉ một lần đổi thông số đột ngột.

## 16. Cách chia phần trình bày và dựng video

Có thể để một người dẫn xuyên suốt. Nếu cả bốn thành viên cùng trình bày, chia
bốn đoạn theo nội dung: bài toán/kiến trúc; simulator/realtime; model/risk/alert;
history/monitoring/GitOps. Phân công tên người nói theo thống nhất của nhóm,
không mặc định thứ tự tên trong bảng là thứ tự phụ trách code.

Khi dựng, giữ lại thời điểm trước/sau thao tác và một đoạn số liệu đang thay đổi.
Cắt phần chờ dài, không cắt ghép làm một alert cũ thành alert vừa tạo hoặc làm
một lỗi thành response thành công. Lời thoại nên đi theo số liệu đang hiển thị;
những chỗ trong ngoặc vuông là chỗ đọc giá trị thực, không phải câu phải đọc nguyên văn.

Sau rehearsal: đưa M-001/M-002 về scenario và trạng thái chạy mong muốn. Các lần
thử tự động đã khôi phục control state ban đầu; alert/audit/history phát sinh hợp
lệ vẫn được giữ để truy vết.


## 17. Cảnh phân quyền tùy chọn, khoảng 45 giây

Mở một cửa sổ ẩn danh đã đăng nhập `viewer`, vào chi tiết alert. Đối chiếu với
cửa sổ `administrator`: viewer xem được dữ liệu trong phạm vi được cấp, nhưng
không có form xử lý dành cho kỹ thuật viên/quản trị viên. Chạy thử trước để chắc
chắn đã chọn đúng tài khoản, không chỉ đổi tên hiển thị trên giao diện.

**Lời thoại:**

> Tài khoản xem chỉ được đọc dữ liệu trong phạm vi đã cấp. Các thao tác tiếp nhận,
> xử lý và đóng cảnh báo dành cho vai trò được phép. Backend kiểm tra token,
> vai trò và phạm vi máy trước khi thực hiện yêu cầu. Việc kiểm tra này vẫn áp dụng
> nếu người dùng gửi request trực tiếp thay vì bấm nút trên giao diện.

Bài kiểm chứng History đã xác nhận thiếu token trả 401 và truy cập máy ngoài
phạm vi trả 403. Không mở phần Authorization hoặc Secret trong bản quay màn hình.
