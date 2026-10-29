# RISK-POLICY-01 — Infrastructure chuyển app source, không sở hữu policy

Source chuẩn: `MaintAI/processing/config/risk-policies/` trong app repo.
Selector: `MaintAI-gitops/config/local/risk-policy.lock.json`, khóa app commit,
policy version/path, checksum file và checksum canonical mà Worker dùng.

Infrastructure không tạo policy, không chọn ngưỡng và không yêu cầu file policy
trong `local/.local/data/fixtures/`. Thư mục fixtures vẫn dùng cho full model
identity cùng các input local khác. Các file model/dataset vẫn ngoài Git.

## Luồng prepare

1. Kiểm app checkout khớp `local/versions/app-source.lock.json`.
2. Kiểm checksum các file host thực sự cần mount, như model identity/dataset/model.
3. Truyền app root qua `--app-root` cho GitOps prepare apps.
4. GitOps kiểm policy source/schema/catalog/selector và tạo ConfigMap read-only.
5. Review/push GitOps; Argo mới đồng bộ ConfigMap và Worker Deployment.

Policy được mount tại `/local/config/risk-policy.json`; Worker được cấp biến
`PROCESSING_RISK_POLICY_FILE` tương ứng. File này đến từ ConfigMap, không từ
hostPath của infrastructure. Đổi content tạo tên ConfigMap mới và Pod rollout.

## Migration profile

- Bỏ `files.risk_policy` hoặc entry `risk-policy.json` của Worker; CLI sẽ từ chối
  khai báo cũ trước khi gọi generator, không cố đọc file private đó.
- Giữ `/local/fixtures/model-identity.json` và checksum thật.
- Không override policy path qua env; không copy policy chỉnh tay để làm đủ gate.
- Commit/push policy app trước khi CI platform checkout SHA mới trong source lock.

`local/tests/test_policy_handoff.py` kiểm việc chuyển source và chặn input cũ
bằng subprocess mocks; nó không tạo cluster hoặc bật app. `demo-risk-v1` là policy
tham khảo chưa calibration, không tự hoàn tất model identity hoặc đảm bảo alert.
