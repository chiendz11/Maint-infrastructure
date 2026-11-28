# Edge Sensor Simulator (Outside k3d over MQTTS :8883)

Compose này chạy `maintai-sensor` bên ngoài cụm `k3d-maintai-local` và kết nối vào EMQX NodePort `127.0.0.1:8883` (`30883`) qua MQTTS + TLS CA local (`local/.local/tls/mqtt-ca.crt`).

## Cách chạy

```bash
kubectl --kubeconfig local/.local/kubeconfig -n maintai-local get secret local-mqtt-tls -o jsonpath='{.data.ca\.crt}' | base64 -d > local/.local/tls/mqtt-ca.crt
export MAINTAI_SENSOR_IMAGE="$(jq -r '.image' local/.local/receipts/sensor.json)"
docker compose -f local/edge-simulator/docker-compose.yml up -d
```

Lưu ý:
- Khi chạy mode edge này, hãy scale `deployment/sensor` trong `maintai-local` về `0` để tránh trùng `machine_id` sequence/epoch.
- `/app/state` được lưu bền vững trong Docker named volume `edge_sensor_state` để giữ nguyên `stream_epoch` và `sequence_number` qua các lần restart (`docker compose down` giữ lại state; chỉ dùng `down -v` sau khi reset DB/Kafka của cụm).
