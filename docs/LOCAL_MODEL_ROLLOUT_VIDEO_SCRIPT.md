# Kịch bản Video Demo: Huấn luyện, Quản lý Vòng đời (MLflow) và Triển khai Shadow Model (GitOps & Traffic Mirroring)

Phiên bản: **2.0 — Cập nhật ngày 07/11/2026**  
Mục tiêu: Kịch bản quay video thực tế (thời lượng 6–8 phút) mô phỏng chính xác vai trò của **Kỹ sư Machine Learning & MLOps** trong dự án MaintAI.

---

## 1. Tổng quan luồng nghiệp vụ MLOps chuẩn mực

Quy trình triển khai mô hình mới trong MaintAI tuân thủ kiến trúc MLOps hiện đại, khép kín từ khâu nghiên cứu tới vận hành thực tế:

```text
[Dataset AI4I] ---> [Stratified Split & Feature Engineering]
                            |
                            v
                   [Huấn luyện Model HGB mới]
                            |
                            v
            [Đánh giá Benchmark Offline (F1: 0.62 -> 0.88)]
                            |
                            v
       [MLflow Tracking & Model Registry (Alias: @shadow)]
                            |
                            v
      [GitOps PR / ArgoCD Reconcile Pod ml-service-shadow]
                            |
                            v
    [Traffic Mirroring: Nhân bản Telemetry thời gian thực]
                            |
                            v
      [Grafana: Giám sát Latency, Dự đoán & Tỷ lệ phân kỳ]
```

---

## 2. Các thành phần và địa chỉ truy cập trong môi trường Demo

| Thành phần | Địa chỉ / Tài nguyên | Mô tả vai trò |
| --- | --- | --- |
| **MLflow UI** | `http://127.0.0.1:15000` | Quản lý thí nghiệm (Tracking) và phiên bản mô hình (Model Registry). |
| **Grafana ML Dashboard** | `http://127.0.0.1:13000` | Giám sát độ trễ suy luận, throughput và so sánh Champion vs Shadow. |
| **Model Champion** | Pod `ml-service` (port `8001`) | Model đang phục vụ sản xuất: `logreg-baseline-v0` (Baseline Logistic Regression). |
| **Model Shadow** | Pod `ml-service-shadow` (port `8001`) | Model ứng viên thử nghiệm: `hgb-interactions-candidate-v1` (HistGradientBoosting). |
| **Dataset AI4I 2020** | `ml-service/training/data_preparation/` | 10.000 điểm dữ liệu cảm biến đo đạc công nghiệp chuẩn hóa. |

---

## 3. Các bước thực hiện chi tiết

### Bước 1: Chuẩn bị dữ liệu và huấn luyện mô hình mới

Kỹ sư ML phân tích dữ liệu cảm biến máy công nghiệp, nhận thấy mối tương quan vật lý giữa nhiệt độ, tốc độ quay, mô-men xoắn và độ mòn dụng cụ:

1. **Phân chia dữ liệu (Stratified Split)**: Giữ nguyên tỷ lệ các loại lỗi hỏng hóc giữa tập Train và Test.
2. **Trích xuất đặc trưng tương tác (Feature Interactions)**:
   * Chênh lệch nhiệt độ: $\Delta T = T_{\text{process}} - T_{\text{air}}$.
   * Công suất cơ học xấp xỉ: $P \approx \text{Torque} \times \text{Rotational Speed}$.
   * Tích tải trọng và độ mòn: $\text{Strain} = \text{Torque} \times \text{Tool Wear}$.
3. **Huấn luyện mô hình HistGradientBoosting (HGB)**:
   * Khả năng học phi tuyến tính vượt trội so với hồi quy tuyến tính cổ điển.

```bash
# Chạy script huấn luyện và đóng gói candidate bundle
python ml-service/training/export/generate_hgb_bundle.py \
  --output-dir ml-service/artifacts/candidate_hgb
```

---

### Bước 2: Đánh giá mô hình trên tập Test độc lập (Evaluation)

So sánh hiệu năng giữa mô hình Baseline hiện tại (Champion) và mô hình mới (Candidate):

| Chỉ số đánh giá | Baseline (`logreg-baseline-v0`) | Ứng viên mới (`hgb-interactions-candidate-v1`) | Nhận xét cải tiến |
| --- | :---: | :---: | --- |
| **F1-Score (Macro)** | **0.625** | **0.884** | Tăng **+41.4%** năng lực phát hiện hỏng hóc |
| **Precision** | 0.714 | 0.892 | Giảm mạnh tỷ lệ báo động giả (False Alarms) |
| **Recall** | 0.556 | 0.876 | Bắt gần như toàn bộ các trường hợp hư hỏng tiềm ẩn |
| **ROC-AUC** | 0.912 | 0.978 | Khả năng phân biệt cực kỳ tách bạch |
| **Decision Threshold** | `0.500` | `0.0894` | Ngưỡng nhạy tối ưu hóa theo ma trận chi phí bảo trì |

---

### Bước 3: Đồng bộ thí nghiệm và đăng ký mô hình lên MLflow

Kết quả huấn luyện và artifact của mô hình được tự động lưu vết (provenance & lineage) lên MLflow:

1. **MLflow Tracking**: Lưu toàn bộ tham số siêu hình thức (hyperparameters), đường cong PR-curve và metrics đánh giá.
2. **MLflow Model Registry**:
   * Model Baseline được gắn nhãn alias: `@champion` (Production).
   * Model HGB mới được tạo bản ghi phiên bản mới với nhãn alias: `@shadow` (Candidate).

```bash
# Ghi nhận kết quả vào MLflow Server local
python ml-service/training/export/log_hgb_experiment.py \
  --benchmark-dir ml-service/artifacts/candidate_hgb
```

*Kiểm tra ngay trên giao diện MLflow*: Mở `http://127.0.0.1:15000` -> Tab **Experiments** thấy 2 Run -> Tab **Models** thấy 2 Registered Models với alias tương ứng.

---

### Bước 4: Triển khai Shadow Model qua GitOps (ArgoCD)

Không can thiệp thủ công vào cụm Kubernetes production, việc cập nhật mô hình Shadow tuân thủ nguyên lý GitOps:

1. Kỹ sư mở PR trên repository `MaintAI-gitops`, cập nhật cấu hình:
   * Đường dẫn Model: `MODEL_DIR: /local/models/hgb-interactions-candidate-v1`
   * Vai trò workload: `SERVICE_ROLE: shadow`
2. Sau khi PR được duyệt và merge, **ArgoCD** tự động phát hiện thay đổi và đồng bộ xuống cụm.
3. Kubernetes tiến hành rollout Pod `ml-service-shadow` với mô hình mới song song cùng Pod `ml-service` (Champion) hiện có.

---

### Bước 5: Kích hoạt Traffic Mirroring và Đánh giá Live trên Grafana

Đây là bước tối quan trọng để Shadow Deployment có ý nghĩa thực tiễn:

1. **Nguyên lý Traffic Mirroring**:
   * Khi Worker nhận telemetry từ cảm biến, một bản sao của request được gửi không đồng bộ (non-blocking) tới `ml-service-shadow`.
   * Model Champion tiếp tục ra quyết định cảnh báo trên giao diện vận hành nhà máy.
   * Model Shadow âm thầm chấm điểm trên luồng dữ liệu thật để chứng minh tính ổn định và đo đạc độ trễ trước khi được thay thế chính thức.

2. **Kích hoạt gửi luồng telemetry đồng thời tới Shadow**:
   ```bash
   # Gửi kiểm thử mẻ telemetry vào Shadow để kích hoạt đường metric
   kubectl --context k3d-maintai-local -n maintai-local exec deploy/ml-service-shadow -c ml-service-shadow -- python3 -c "
   import urllib.request, json, time
   for i in range(50):
       payload = {'event_id': f'evt_demo_{i}', 'machine_id': 'M-001', 'features': {'air_temperature_k': 300.0 + (i % 5), 'process_temperature_k': 310.0 + (i % 3), 'rotational_speed_rpm': 1400 - i * 4, 'torque_nm': 45.0 + i * 0.5, 'tool_wear_min': i * 2, 'product_type': 'L'}}
       req = urllib.request.Request('http://127.0.0.1:8001/api/v1/predict', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
       with urllib.request.urlopen(req) as r: pass
       time.sleep(0.05)
   print('Hoàn tất gửi luồng telemetry sang Shadow!')
   "
   ```

3. **Quan sát trên Grafana ML Dashboard (`http://127.0.0.1:13000`)**:
   * **Inference Request Throughput**: Thấy rõ lưu lượng của cả Champion và Shadow.
   * **Inference Latency p95**: Chứng minh độ trễ suy luận của Shadow cực thấp (~**12ms**), hoàn toàn đáp ứng yêu cầu xử lý thời gian thực của dây chuyền công nghiệp.
   * **Predictions Breakdown**: So sánh tỷ lệ dự đoán lỗi giữa hai mô hình trên cùng dữ liệu đầu vào.

---

## 4. Kịch bản và Lời thoại chi tiết khi quay Video (6 – 8 phút)

Bố cục màn hình đề xuất khi quay:
* Nửa trái màn hình: Trình duyệt mở sẵn các tab (MLflow UI, Grafana ML Dashboard, Business Frontend).
* Nửa phải màn hình: Terminal thao tác kiểm tra lệnh.

---

### Cảnh 1: Đặt vấn đề và giới thiệu Dữ liệu (00:00 – 01:15)
* **Bối cảnh & Thao tác**: Mở giao diện Business UI (`http://127.0.0.1:18080`) cho thấy 5 máy đang vận hành bình thường; mở Terminal kiểm tra trạng thái cụm và mẫu dữ liệu cảm biến.
* **Lệnh Terminal thực thi**:
  ```bash
  # 1. Kiểm tra trạng thái toàn bộ các pod trong cụm k3d (đảm bảo môi trường sẵn sàng)
  kubectl get pods -n maintai-local

  # 2. Xem cấu trúc dữ liệu cảm biến công nghiệp AI4I 2020
  head -n 5 sensor/data/ai4i2020.csv

  # 3. Thống kê tổng số bản ghi trong tập dữ liệu (10.000 mẫu đo cảm biến)
  wc -l sensor/data/ai4i2020.csv
  ```
* **Lời thoại**:
  > *"Kính thưa thầy cô, trong hệ thống bảo trì dự đoán MaintAI, mô hình máy học đóng vai trò trái tim để phát hiện sớm các nguy cơ hư hỏng của thiết bị trước khi sự cố xảy ra.*
  >
  > *Hiện tại, hệ thống đang phục vụ vận hành bằng một mô hình Baseline tuyến tính (`logreg-baseline-v0`). Tuy nhiên, trong môi trường sản xuất thực tế, các tương tác vật lý giữa nhiệt độ quy trình, tốc độ quay của trục chính và độ mòn dụng cụ cắt gọt có tính phi tuyến rất phức tạp.*
  >
  > *Hôm nay, nhóm em xin trình bày quy trình MLOps hoàn chỉnh: từ khâu phân tích dữ liệu, nghiên cứu mô hình mới có trích xuất tương tác đặc trưng, theo dõi trên MLflow, cho đến việc triển khai an toàn dưới dạng Shadow Model trong cụm Kubernetes bằng GitOps."*

---

### Cảnh 2: Huấn luyện và Đánh giá Offline (01:15 – 02:45)
* **Bối cảnh & Thao tác**: Mở Terminal hiển thị logic Feature Interactions, cấu hình siêu tham số và kết quả benchmark của Candidate model.
* **Lệnh Terminal thực thi**:
  ```bash
  # 1. Xem bộ biến đổi tương tác vật lý (Feature Interactions: Delta T, cơ năng, ứng suất cắt)
  head -n 25 ml-service/shared/preprocessing/feature_interactions.py

  # 2. Xem cấu hình siêu tham số và kết quả đánh giá offline (F1: 0.88, Recall: 87.6%)
  cat ml-service/artifacts/integration/hgb-interactions-m56w5ff4/metadata.json | jq '{model_version, features, derived_features, threshold, validation_metrics}'

  # 3. Kiểm tra Quality Gate tự động của mô hình mới đạt trạng thái PASS
  cat ml-service/artifacts/integration/hgb-interactions-m56w5ff4/evaluation.json | jq .quality_gate
  ```
* **Lời thoại**:
  > *"Nhóm sử dụng bộ dữ liệu AI4I 2020 gồm 10.000 mẫu đo cảm biến thực tế từ máy CNC. Dữ liệu được phân chia theo phương pháp Stratified Split để bảo toàn tỷ lệ các loại lỗi hỏng hóc.*
  >
  > *Điểm cải tiến kỹ thuật ở phiên bản này là nhóm xây dựng thêm bộ biến đổi tương tác đặc trưng (`Feature Interactions`)—chẳng hạn như tích giữa mô-men xoắn và độ mòn dụng cụ để biểu diễn ứng suất cơ học.*
  >
  > *Kết quả huấn luyện mô hình HistGradientBoosting mới cho thấy sự vượt trội toàn diện: Chỉ số F1-Score tăng mạnh từ 0.62 lên 0.88, độ bao phủ lỗi (Recall) đạt 87.6% so với 55.6% của mô hình cũ. Đồng thời, ngưỡng quyết định được tối ưu hóa ở mức 0.089 để tăng tối đa độ nhạy đối với các dấu hiệu hư hại ban đầu."*

---

### Cảnh 3: Quản lý Vòng đời Mô hình trên MLflow (02:45 – 04:15)
* **Bối cảnh & Thao tác**: Chuyển sang trình duyệt tab **MLflow UI (`http://127.0.0.1:15000`)**, đồng thời chạy lệnh kiểm tra API của MLflow để minh chứng tính tự động hóa.
* **Lệnh Terminal thực thi**:
  ```bash
  # 1. Kiểm tra thí nghiệm 'predictive-maintenance' đã đăng ký trên MLflow
  curl -s "http://127.0.0.1:15000/api/2.0/mlflow/experiments/search?max_results=10" | jq '.experiments[] | {id: .experiment_id, name: .name}'

  # 2. Xem chi tiết các lần chạy (Runs) và so sánh metrics Champion vs Candidate
  curl -s -X POST "http://127.0.0.1:15000/api/2.0/mlflow/runs/search" \
    -H "Content-Type: application/json" \
    -d '{"experiment_ids": ["1"]}' | jq -r '.runs[] | {run_id: .info.run_id, model: (.data.tags[] | select(.key=="mlflow.runName") | .value), metrics: .data.metrics}'

  # 3. Liệt kê Model Registry và xác minh phân định Alias (@champion vs @shadow)
  curl -s http://127.0.0.1:15000/api/2.0/mlflow/registered-models/search | jq -r '.registered_models[] | {model_name: .name, latest_version: .latest_versions[0].version, aliases: .aliases}'
  ```
* **Lời thoại**:
  > *"Sau khi huấn luyện thành công, toàn bộ thông số thực nghiệm và tệp đóng gói mô hình được tự động lưu vết trên MLflow Server.*
  >
  > *Tại tab Experiments, thầy cô có thể thấy hai lượt chạy được ghi nhận rõ ràng: lượt chạy Champion của mô hình cũ và lượt chạy Candidate của mô hình mới với biểu đồ so sánh chi tiết các chỉ số F1, Precision và ROC-AUC.*
  >
  > *Tại tab Models (Model Registry), nhóm quản lý phiên bản với cơ chế Alias rõ ràng: Mô hình Baseline mang nhãn `@champion` đại diện cho phiên bản đang chịu tải chính, trong khi mô hình HistGradientBoosting mới được đăng ký phiên bản 1 với nhãn `@shadow` đại diện cho ứng viên đang chuẩn bị thử nghiệm."*

---

### Cảnh 4: Triển khai Shadow Model qua GitOps & ArgoCD (04:15 – 05:45)
* **Bối cảnh & Thao tác**: Mở file cấu hình GitOps/màn hình ArgoCD, sau đó mở Terminal kiểm tra trạng thái Pods và Readiness Probe trong Kubernetes.
* **Lệnh Terminal thực thi**:
  ```bash
  # 1. Xác minh cấu hình workload Shadow trong Kubernetes (MODEL_DIR và SERVICE_ROLE)
  kubectl get deployment ml-service-shadow -n maintai-local -o jsonpath='{.spec.template.spec.containers[0].env}' | jq .

  # 2. Kiểm tra hai Pod ml-service (Champion) và ml-service-shadow (Shadow) đang chạy song song
  kubectl get pods -n maintai-local -l "app.kubernetes.io/name in (ml-service, ml-service-shadow)" -o wide

  # 3. Kiểm tra kiểm tra mức độ sẵn sàng (Readiness Probe) của cả hai model
  kubectl exec -i deploy/ml-service -n maintai-local -- python3 -c "import urllib.request; print('Champion Readiness:', urllib.request.urlopen('http://127.0.0.1:8001/health/ready').read().decode())"
  kubectl exec -i deploy/ml-service-shadow -n maintai-local -- python3 -c "import urllib.request; print('Shadow Readiness:  ', urllib.request.urlopen('http://127.0.0.1:8001/health/ready').read().decode())"
  ```
* **Lời thoại**:
  > *"Để đưa mô hình mới vào cụm máy chủ mà không làm gián đoạn dây chuyền sản xuất, nhóm áp dụng chiến lược Shadow Deployment (Dark Launch) thông qua GitOps.*
  >
  > *Cấu hình của workload `ml-service-shadow` được cập nhật trong repo GitOps để trỏ tới gói mô hình mới. Ngay lập tức, ArgoCD phát hiện thay đổi và đồng bộ trạng thái mong muốn xuống cụm k3d.*
  >
  > *Trên terminal, thầy cô có thể thấy hai Pod: `ml-service` (Champion) và `ml-service-shadow` (Shadow) đang cùng chạy song song (`1/1 Running`) trong cùng một namespace."*

---

### Cảnh 5: Traffic Mirroring & Kiểm chứng trên Grafana (05:45 – 07:15)
* **Bối cảnh & Thao tác**: Chuyển sang tab **Grafana ML Dashboard (`http://127.0.0.1:13000`)**, mở Terminal so sánh metric và chạy lệnh bắn luồng telemetry vào Shadow để quan sát biểu đồ.
* **Lệnh Terminal thực thi**:
  ```bash
  # 1. Kiểm tra Pod Traffic Mirroring đang nhận diện và forward dữ liệu từ Kafka topic
  kubectl get pods -n maintai-local -l app.kubernetes.io/name=ml-service-shadow-mirror

  # 2. So sánh tổng số lượng request suy luận thực tế (Prometheus metrics) giữa Champion và Shadow
  kubectl exec -i deploy/ml-service -n maintai-local -- python3 -c "import urllib.request; print('Champion:', [l for l in urllib.request.urlopen('http://127.0.0.1:8001/metrics').read().decode().splitlines() if 'maintai_ml_predictions_total' in l])"
  kubectl exec -i deploy/ml-service-shadow -n maintai-local -- python3 -c "import urllib.request; print('Shadow:  ', [l for l in urllib.request.urlopen('http://127.0.0.1:8001/metrics').read().decode().splitlines() if 'maintai_ml_predictions_total' in l])"

  # 3. Bắn mẻ 50 mẫu telemetry vào Shadow để kích hoạt đường biểu đồ biến động trực tiếp trên Grafana
  kubectl exec -i deploy/ml-service-shadow -n maintai-local -- python3 -c "
  import urllib.request, json, time
  print('Đang gửi 50 telemetry readings vào ml-service-shadow...')
  for i in range(50):
      payload = {
          'event_id': f'evt_live_test_{i}',
          'machine_id': 'M-001',
          'features': {
              'air_temperature_k': 300.0 + (i % 5),
              'process_temperature_k': 310.0 + (i % 3),
              'rotational_speed_rpm': 1400 - i * 4,
              'torque_nm': 45.0 + i * 0.5,
              'tool_wear_min': i * 4,
              'product_type': 'L'
          }
      }
      req = urllib.request.Request('http://127.0.0.1:8001/api/v1/predict', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
      with urllib.request.urlopen(req) as r:
          pass
      time.sleep(0.04)
  print('Hoàn tất! Kiểm tra biểu đồ Grafana: Inference Throughput & Latency p95 (~12ms).')
  "
  ```
* **Lời thoại**:
  > *"Điểm cốt lõi của Shadow Deployment là mô hình mới được kiểm thử bằng chính dữ liệu thật từ nhà máy thông qua cơ chế Traffic Mirroring.*
  >
  > *Trong khi Champion vẫn phục vụ suy luận luồng chính cho Business API để hiển thị trạng thái máy lên Dashboard, luồng telemetry cũng được sao chép sang Pod Shadow để đánh giá ngầm.*
  >
  > *Trên màn hình Grafana, cả hai mô hình Champion và Shadow đều đang hiển thị trạng thái `UP`. Nhóm thực hiện truyền tải các gói dữ liệu kiểm thử:*
  > *(Thao tác chạy lệnh gửi dữ liệu trên Terminal -> Grafana cập nhật đường biểu đồ)*
  >
  > *Nhìn vào bảng điều khiển, thời gian suy luận p95 của Shadow chỉ vào khoảng 12ms—cực kỳ nhanh và ổn định. Đồng thời, biểu đồ Predictions Breakdown cho thấy Shadow bắt được các tín hiệu lỗi sớm hơn nhờ ngưỡng suy luận nhạy, hoàn toàn không gây bất kỳ độ trễ hay lỗi nào cho luồng vận hành chính thức."*

---

### Cảnh 6: Kết luận và Định hướng Blue/Green Switch (07:15 – 07:45)
* **Bối cảnh & Thao tác**: Quay lại giao diện Business Workspace tổng quan (`http://127.0.0.1:18080`).
* **Lệnh Terminal thực thi**:
  ```bash
  # 1. Kiểm tra lại trạng thái ổn định toàn diện của cụm sau quá trình Shadow Rollout
  kubectl get pods -n maintai-local

  # 2. Quy trình thăng hạng (Promotion) từ Shadow sang Champion chính thức qua GitOps:
  # (Chỉ cần đổi MODEL_DIR của deploy/ml-service từ logreg-baseline sang hgb-candidate)
  # git checkout -b promote-hgb-champion
  # sed -i 's/logreg-baseline-v0/hgb-interactions-candidate-v1/g' workloads/ml-service/workload.yaml
  # git commit -m "feat(ml): promote hgb-interactions-candidate-v1 to champion"
  # git push origin promote-hgb-champion
  ```
* **Lời thoại**:
  > *"Như vậy, nhóm đã chứng minh thành công chuỗi giá trị MLOps hoàn chỉnh: Từ cải tiến mô hình học máy dựa trên dữ liệu cảm biến, quản lý phiên bản minh bạch trên MLflow, đến việc triển khai an toàn không rủi ro bằng Shadow Deployment qua GitOps.*
  >
  > *Sau giai đoạn theo dõi Shadow trên dữ liệu thực tế và xác nhận độ tin cậy, người quản trị có thể tự tin thực hiện chuyển đổi Blue/Green để thăng hạng Shadow thành Champion chính thức.*
  >
  > *Em xin kết thúc phần trình bày về quy trình MLOps và Shadow Rollout. Cảm ơn thầy cô đã lắng nghe!"*

---

## 5. Bảng kiểm tra trước khi bấm máy quay (Checklist)

- [x] Cụm k3d đang hoạt động bình thường, tất cả các Pod trong `maintai-local` ở trạng thái `Running`.
- [x] `mlflow` pod đang chạy và port-forward sẵn sàng tại `127.0.0.1:15000`.
- [x] Đã có 2 model trong MLflow Registry: `logreg-baseline` (@champion) và `hgb-interactions-candidate` (@shadow).
- [x] `grafana` pod đang chạy, mở được Dashboard ML tại `127.0.0.1:13000`.
- [x] Đã kiểm tra gọi thử endpoint `/api/v1/predict` của `ml-service-shadow` trả về HTTP 200 OK.
