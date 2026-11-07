# Kịch bản train local, MLflow và triển khai candidate qua GitOps

Phiên bản 1.0 — 07/11/2026. Bổ sung cho [video chính](LOCAL_DEMO_VIDEO_SCRIPT.md).
Đọc theo thứ tự các bước để rehearsal; phần lời thoại ở mục 9 dành cho lúc quay.

**Phạm vi:** tài liệu và các mẫu lệnh được viết từ source hiện có. Chưa chạy
training, upload MLflow, build/import image hoặc thay đổi cluster trong lượt viết
này. Các chỗ yêu cầu số đo/ID phải lấy từ lượt chạy thật, không dùng kết quả của
người phát triển ML trên một server khác làm kết quả của laptop này.

Thực hiện từng khối lệnh, dừng ngay nếu một bước lỗi. Nên dùng một shell riêng
cho rehearsal với `set -euo pipefail`; không dán cả tài liệu để bỏ qua các điểm
review, số PR cần điền hoặc thao tác ở các terminal riêng.

## 1. Luồng cần trình bày và trạng thái thực tế

```text
Source MaintAI ở một Git commit cụ thể + AI4I đã kiểm checksum/split
          |
          v
Train HGB local -> bundle mới + validation + drift reference từ train
          |
          +--> MLflow SDK: run, params, metrics, artifacts, Registry candidate
          |                       |
          |                 upload/download kiểm SHA và khả năng load
          v
Image inference tương thích + bundle đặt trong local model volume
          |
          v
Git branch + PR tại MaintAI-gitops (chỉ sửa shadow)
          |
          v
Review/CI -> merge vào revision Argo đang theo dõi -> Argo sync
          |
          v
Shadow Pod Ready -> gọi predict thật -> quan sát metrics -> rollback có version
```

**GitHub không đẩy model vào MLflow chỉ nhờ `git push`.** SDK trên máy train gửi
run/artifacts tới MLflow qua HTTP. GitHub lưu source, PR và desired state. Image
registry giữ image inference. Với local hiện tại, model bundle được mount từ
laptop; Argo không tải thư mục model từ Git hoặc từ MLflow thay cho bước chuẩn bị.

| Phần đã đọc trong repo | Điều cần hiểu trước khi quay |
| --- | --- |
| `generate_hgb_bundle.py` | Có fit HGB, validation, xuất bundle và reference; ghi vào hai đường dẫn cố định, nên dưới đây chạy trong sandbox với hai output mới |
| `MODEL_CARD_HGB.md` | Candidate HGB có test reuse và `approved_for_release=false`; validation đạt gate chưa phải phê duyệt thay model chính |
| `log_hgb_experiment.py`, `register_local_hgb.py` | Là importer của bộ evidence đã freeze, URI cố định `127.0.0.1:5000`, có SHA guard; không dùng cho mọi lần train mới |
| `dispatch_shadow_pr.py` | Chưa tạo PR/cập nhật workload thật; còn dùng metrics mặc định khi thiếu. Không dùng output của script này làm bằng chứng gate hoặc rollout |
| `publish-and-deploy.yml` | Matrix hiện có 10 service khác, chưa có ML inference/training; bước update image còn rộng hơn tập service build. Không dispatch workflow này như một publisher ML đã hoàn tất |
| `sync-platform-locks.yml` | Đồng bộ source locks, không upload model vào MLflow và không phát hành model bundle |
| `localdev model-identity` | Đang hỗ trợ baseline Logreg và marker `not-recorded:local-demo`; chưa phải bộ phát hành HGB có MLflow identity |
| `ml-traffic-mirror.yaml` | Có mẫu Traefik/Istio; file tồn tại không chứng minh đường request hiện tại đã mirror sang shadow |

Vì vậy, kịch bản này triển khai **candidate riêng để thử local**. Không tự chuyển
candidate thành champion, không tự sửa alias MLflow và không cho shadow tạo
prediction/alert nghiệp vụ trong Business.

## 2. Kiểm tra MLflow trước khi tạo run

### 2.1. Đúng server, đúng version và đúng phạm vi lưu trữ

Manifest local hiện được đọc tại
`MaintAI-gitops/environments/local/apps/generated/mlflow.yaml` đang khai báo:

- Image `ghcr.io/mlflow/mlflow:v2.19.0`.
- Backend `sqlite:////tmp/mlflow.db` và artifacts `/tmp/artifacts`.
- Chưa có volume bền vững cho hai đường dẫn đó.

Đây là cấu hình source, không thay cho kiểm tra Pod đang chạy. Metadata và
artifacts trong filesystem container có thể mất khi container/Pod được tạo lại;
không dùng run ở đây làm bằng chứng đã kiểm thử persistence. Trước buổi quay dài,
nên hoàn thiện backend PostgreSQL và artifact storage hoặc PVC riêng qua PR
platform; giữ dữ liệu cũ và kiểm tra restore, không coi đổi URI là tự migrate DB.
Tài liệu này không tự thay cấu hình lưu trữ hoặc nâng phiên bản server.

Từ infrastructure, dùng kubeconfig local:

```bash
cd /home/chienqt/Dev/newBTL/Maint-infrastructure
set -euo pipefail
k() {
  kubectl --kubeconfig "$PWD/local/.local/kubeconfig" \
    --context k3d-maintai-local "$@"
}
k -n maintai-local get deployment mlflow
k -n maintai-local get deployment mlflow \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
curl --fail --silent --show-error http://127.0.0.1:15000/health
curl --fail --silent --show-error http://127.0.0.1:15000/version
```

Nếu port 15000 chưa được forward, ở terminal riêng dùng:

```bash
k -n maintai-local port-forward --address 127.0.0.1 service/mlflow 15000:5000
```

Không mở hai forward cùng một port. Browser/host dùng `127.0.0.1:15000`; một Pod
trong namespace dùng `http://mlflow:5000`. Hai địa chỉ này phải đi tới cùng server.

### 2.2. SDK của mẫu operator này

Bộ ML bàn giao ghi SDK/server 3.17.1 trên máy người tạo. Không suy rằng dữ liệu và
server đó đã được chuyển vào k3d. Để không trộn môi trường, mẫu uploader dưới đây
là **profile local riêng cho server 2.19.0 hiện khai báo**: dùng
`mlflow-skinny==2.19.0` và dependencies serving. Đây không phải thay lock training
3.17.1 của app hoặc xác nhận cặp thư viện đã được kiểm chứng production.

Script kiểm tra version, upload/download, load Registry và so score. Nếu bước
kiểm tra nào không đạt thì dừng; không bỏ guard hoặc đổi hash cho qua. Nếu server
đã được nâng cấp, owner phải cập nhật/review SDK profile tương ứng trước khi dùng.
API tham khảo: [MlflowClient 2.19.0](https://mlflow.org/docs/2.19.0/python_api/mlflow.client.html).

## 3. Chuẩn bị source và train HGB local

### 3.1. Tạo source checkout riêng, giữ nguyên working tree đang phát triển

Các biến `roll_*` dưới đây dùng trong cùng terminal. Không commit/reset thay đổi
đang có của người khác. Chọn commit đã được nhóm review; `origin/main` chỉ là
ví dụ điểm lấy source, không thay quyết định phê duyệt model.

```bash
roll_parent=/home/chienqt/Dev/newBTL
roll_infra="$roll_parent/Maint-infrastructure"
roll_app_repo="$roll_parent/MaintAI"
git -C "$roll_app_repo" fetch origin main
roll_sha=$(git -C "$roll_app_repo" rev-parse origin/main)
roll_app="$roll_parent/MaintAI-rollout-source-${roll_sha:0:12}"
git -C "$roll_app_repo" worktree add --detach "$roll_app" "$roll_sha"

umask 022
roll_private=$(mktemp -d "$roll_infra/local/.local/model-rollout.XXXXXX")
mkdir -p "$roll_private/bundle" "$roll_private/secondary-output" "$roll_private/evidence"
```

Nếu worktree đã tồn tại, kiểm tra HEAD và working tree rồi dùng lại có chủ đích;
không tự xóa để lệnh chạy lại. Output mỗi lần train phải ở thư mục mới.

Đặt dataset vào đường dẫn mà script ML đọc. File CSV nằm ngoài nội dung commit:

```bash
mkdir -p "$roll_app/sensor/data"
if test -e "$roll_app/sensor/data/ai4i2020.csv"; then
  cmp "$roll_infra/local/.local/data/datasets/ai4i2020.csv" \
      "$roll_app/sensor/data/ai4i2020.csv"
else
  install -m 644 "$roll_infra/local/.local/data/datasets/ai4i2020.csv" \
      "$roll_app/sensor/data/ai4i2020.csv"
fi
```

Chỉ tiếp tục nếu copy/cmp thành công. Không push AI4I hoặc pipeline.joblib lên Git.

### 3.2. Build môi trường ML tương thích, không dùng batch entrypoint nhầm mục đích

Inference Dockerfile chứa sklearn và transformer cần để chạy HGB. Ở đây dùng
chính image đó làm môi trường chạy script train local; không gọi đây là bằng
chứng training image/Argo batch entrypoint đã hoàn tất.

```bash
docker build \
  --file "$roll_app/ml-service/inference/Dockerfile" \
  --label "org.opencontainers.image.revision=$roll_sha" \
  --tag "maintai-local/ml-rollout-source:git-$roll_sha" \
  "$roll_app"
roll_image="maintai-local/ml-rollout-source:git-$roll_sha"
```

Chỉ chạy tiếp khi build thành công. Không cần push image lên ECR để rehearsal
local; mục 6 dùng import vào đúng cluster. Publisher ML trên GitHub là bước
riêng, chưa được tạo bằng việc chạy một workflow build service khác.

### 3.3. Kiểm frozen split rồi fit trong sandbox

Script có hai output cố định. Chuẩn bị mount points để cả hai đều trỏ vào output
mới, tránh ghi đè bundle đang phục vụ:

```bash
mkdir -p "$roll_app/ml-service/artifacts/integration/hgb-interactions-m56w5ff4"
docker run --rm --network none --read-only --tmpfs /tmp \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$roll_app,dst=/work/source,readonly" \
  "$roll_image" python \
  /work/source/ml-service/training/data_preparation/create_split.py --verify-only
```

Verifier phải pass trước khi fit. Lệnh fit:

```bash
docker run --rm --network none --read-only --tmpfs /tmp \
  --user "$(id -u):$(id -g)" \
  -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 \
  --mount "type=bind,src=$roll_app,dst=/work/source,readonly" \
  --mount "type=bind,src=$roll_private/bundle,dst=/work/source/ml-service/artifacts/integration/hgb-interactions-m56w5ff4" \
  --mount "type=bind,src=$roll_private/secondary-output,dst=/models/candidate_dest" \
  "$roll_image" python \
  /work/source/ml-service/training/export/generate_hgb_bundle.py
```

Đọc metrics thực trên terminal. Script fit chỉ trên train, đo validation và dùng
threshold HGB cố định đã chọn trước đó; đây không phải một lần chọn threshold
mới độc lập. Reference lấy từ train. Không mở test để tối ưu model trong buổi quay.

Bundle chính ở `$roll_private/bundle`, gồm pipeline, metadata, evaluation,
reference, transformer và manifest. Output phụ giữ riêng; không dùng lẫn file
của hai output. Cả hai đều là candidate chưa được phê duyệt release.

## 4. Ghi kết quả mới vào MLflow và Registry

### 4.1. Tạo môi trường uploader riêng

```bash
python3.12 -m venv "$roll_private/uploader-venv"
roll_python="$roll_private/uploader-venv/bin/python"
"$roll_python" -m pip install \
  -r "$roll_app/ml-service/inference/requirements-serving.txt" \
  'mlflow-skinny==2.19.0'
"$roll_python" -m pip check
"$roll_python" -m pip freeze > "$roll_private/evidence/uploader-environment.txt"
export MLFLOW_TRACKING_URI=http://127.0.0.1:15000
export MLFLOW_REGISTRY_URI="$MLFLOW_TRACKING_URI"
export MLFLOW_HTTP_REQUEST_TIMEOUT=30
export MLFLOW_HTTP_REQUEST_MAX_RETRIES=0
```

Đây là môi trường operator để rehearsal, chưa là lock đầy đủ đã được CI kiểm
cho pipeline production. Giữ snapshot môi trường cùng evidence. Không dùng
credential/API key làm Docker build arg hoặc đưa vào Git.

### 4.2. Mẫu uploader có receipt, kiểm tra dữ liệu thật

Tạo file private; file này là mẫu operator trong tài liệu, không giả rằng app đã
có trainer ledger production. Nó không sửa bundle, không retry create POST khi
không rõ kết quả và không đặt alias champion.

```bash
cat > "$roll_private/track_candidate.py" <<'PY'
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request

import joblib
import mlflow
import mlflow.sklearn
from mlflow.entities import Metric, Param
from mlflow.models import infer_signature
from mlflow.tracking import MlflowClient
import numpy as np
import pandas as pd

bundle, source, evidence = map(lambda x: Path(x).resolve(), sys.argv[1:4])
receipt_path = evidence / 'mlflow-receipt.json'
if receipt_path.exists():
    raise SystemExit('Receipt exists: reconcile the recorded operation before retrying.')
uri = os.environ['MLFLOW_TRACKING_URI']
if uri != 'http://127.0.0.1:15000' or os.environ['MLFLOW_REGISTRY_URI'] != uri:
    raise SystemExit('This operator example is scoped to the loopback local server.')
with urllib.request.urlopen(uri + '/version', timeout=10) as response:
    server_version = response.read(100).decode().strip()
if server_version != '2.19.0' or mlflow.__version__ != '2.19.0':
    raise SystemExit('Review the SDK/server profile before continuing.')
mlflow.set_tracking_uri(uri)
mlflow.set_registry_uri(uri)
client = MlflowClient(tracking_uri=uri, registry_uri=uri)
experiment = client.get_experiment_by_name('Default')
if experiment is None:
    raise SystemExit('Provision/review the local experiment before creating a run.')

def read(path):
    return json.loads(path.read_text())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

metadata = read(bundle / 'metadata.json')
evaluation = read(bundle / 'evaluation.json')
manifest = read(bundle / 'bundle-manifest.json')
reference = read(bundle / 'drift_reference.json')
for name, expected in manifest['files'].items():
    path = (bundle / name).resolve()
    if not path.is_relative_to(bundle) or not path.is_file() or sha(path) != expected:
        raise ValueError('Bundle manifest verification failed')
if sha(bundle / 'pipeline.joblib') != metadata['pipeline_sha256']:
    raise ValueError('Pipeline hash differs from metadata')
transformer = source / 'ml-service/shared/preprocessing/feature_interactions.py'
split = source / 'ml-service/training/data_preparation/splits/ai4i-stratified-v1-seed42.json'
data = source / 'sensor/data/ai4i2020.csv'
for path, field in [(transformer, 'transformer_sha256'), (split, 'split_sha256'),
                    (data, 'source_sha256')]:
    if sha(path) != metadata[field]:
        raise ValueError('Training source/data identity mismatch: ' + field)
if metadata['approved_for_release'] is not False or evaluation['approved_for_release'] is not False:
    raise ValueError('This example records an unapproved local candidate only')
if reference['model_version'] != metadata['model_version'] or reference['dataset_version'] != metadata['dataset_version']:
    raise ValueError('Drift reference identity mismatch')
metrics = evaluation['metrics']
if any(type(x) not in (int, float) or not math.isfinite(x) for x in metrics.values()):
    raise ValueError('Invalid measured metric')
gate = metrics['recall_failure'] >= .85 and metrics['precision_failure'] >= .50
if (evaluation['quality_gate']['status'] == 'PASS') != gate:
    raise ValueError('Quality gate does not match the measured metrics')
source_sha = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
sys.path.insert(0, str(transformer.parent))
pipeline = joblib.load(bundle / 'pipeline.joblib')
column_map = {'Type': 'product_type', 'Air temperature [K]': 'air_temperature_k',
              'Process temperature [K]': 'process_temperature_k',
              'Rotational speed [rpm]': 'rotational_speed_rpm',
              'Torque [Nm]': 'torque_nm', 'Tool wear [min]': 'tool_wear_min'}
frame = pd.read_csv(data).iloc[read(split)['indices']['validation']][list(column_map)].rename(columns=column_map)
for name in list(column_map.values())[1:]:
    frame[name] = frame[name].astype('float64')
expected_scores = pipeline.predict_proba(frame)
package = evidence / 'registry-model'
mlflow.sklearn.save_model(sk_model=pipeline, path=str(package),
    code_paths=[str(transformer)], input_example=frame.head(3),
    signature=infer_signature(frame, expected_scores),
    serialization_format='cloudpickle', pyfunc_predict_fn='predict_proba',
    pip_requirements=[line for line in (source / 'ml-service/inference/requirements-serving.txt').read_text().splitlines()
                      if line and not line.startswith('#')] + ['mlflow-skinny==2.19.0'])
package_hashes = {p.relative_to(package).as_posix(): sha(p)
                  for p in sorted(package.rglob('*')) if p.is_file()}
(evidence / 'registry-package-manifest.json').write_text(json.dumps(package_hashes, indent=2) + '\n')
receipt = {'state': 'CREATE_RUN_INTENT', 'scope': 'local-shadow-rehearsal',
           'server_version': server_version, 'tracking_uri': uri,
           'source_git_sha': source_sha, 'pipeline_sha256': metadata['pipeline_sha256'],
           'bundle_manifest_sha256': sha(bundle / 'bundle-manifest.json'),
           'approved_for_release': False, 'validation_gate_passed': gate}

def checkpoint(state, **values):
    receipt.update(state=state, **values)
    tmp = receipt_path.with_suffix('.tmp')
    tmp.write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n')
    tmp.replace(receipt_path)

with receipt_path.open('x') as stream:
    json.dump(receipt, stream, indent=2)
run = client.create_run(experiment.experiment_id,
    run_name='local-hgb-rollout-' + metadata['pipeline_sha256'][:12],
    tags={'maintai.scope': 'local-shadow-rehearsal',
          'maintai.approved_for_release': 'false',
          'maintai.evaluation_scope': 'validation_reused',
          'maintai.independent_new_holdout': 'false',
          'maintai.source_git_sha': source_sha,
          'maintai.pipeline_sha256': metadata['pipeline_sha256']})
run_id = run.info.run_id
checkpoint('RUN_CREATED', run_id=run_id)
params = {**metadata['model_params'], 'threshold': metadata['threshold'],
          'model_version': metadata['model_version'],
          'dataset_sha256': metadata['source_sha256'], 'split_sha256': metadata['split_sha256']}
client.log_batch(run_id, params=[Param(k, str(v)) for k, v in params.items()],
    metrics=[Metric('validation.' + k, float(v), int(time.time()*1000), 0) for k, v in metrics.items()],
    synchronous=True)
client.log_artifacts(run_id, str(bundle), artifact_path='serving-bundle')
client.log_artifacts(run_id, str(package), artifact_path='model')
client.log_artifact(run_id, str(evidence / 'registry-package-manifest.json'), artifact_path='provenance')
for name in ['uploader-environment.txt', 'track_candidate.py']:
    path = evidence / name if name.endswith('.txt') else evidence.parent / name
    if path.is_file():
        client.log_artifact(run_id, str(path), artifact_path='provenance')
recorded = client.get_run(run_id)
for key, value in params.items():
    if recorded.data.params.get(key) != str(value):
        raise ValueError('Tracking parameter read-back mismatch')
for key, value in metrics.items():
    actual = recorded.data.metrics.get('validation.' + key)
    if actual is None or not math.isclose(actual, value, rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError('Tracking metric read-back mismatch')

def verify_download(folder, hashes):
    for name, expected in hashes.items():
        if sha(Path(folder) / name) != expected:
            raise ValueError('Artifact download hash mismatch: ' + name)

with tempfile.TemporaryDirectory() as directory:
    downloaded = client.download_artifacts(run_id, 'serving-bundle', directory)
    verify_download(downloaded, {p.relative_to(bundle).as_posix(): sha(p)
                               for p in bundle.rglob('*') if p.is_file()})
client.set_terminated(run_id, status='FINISHED')
name = 'maintai-local-rollout-' + run_id[:12]
checkpoint('CREATE_REGISTERED_MODEL_INTENT', registered_model_name=name)
client.create_registered_model(name, tags={'maintai.approved_for_release': 'false'})
checkpoint('CREATE_MODEL_VERSION_INTENT')
version = client.create_model_version(name=name, source=f'runs:/{run_id}/model',
    run_id=run_id, tags={'maintai.approved_for_release': 'false'}, await_creation_for=0)
checkpoint('VERSION_CREATED', registered_model_version=str(version.version))
deadline = time.monotonic() + 60
while True:
    resolved = client.get_model_version(name, str(version.version))
    if resolved.status == 'READY':
        break
    if resolved.status == 'FAILED_REGISTRATION' or time.monotonic() >= deadline:
        raise RuntimeError('Registry failed or did not become READY within the budget')
    time.sleep(2)
if resolved.run_id != run_id:
    raise ValueError('Registry run mismatch')
model_uri = f'models:/{name}/{version.version}'
with tempfile.TemporaryDirectory() as directory:
    downloaded = mlflow.artifacts.download_artifacts(artifact_uri=model_uri, dst_path=directory)
    verify_download(downloaded, package_hashes)
    loaded = mlflow.sklearn.load_model(downloaded)
    np.testing.assert_allclose(loaded.predict_proba(frame), expected_scores, rtol=1e-10, atol=1e-10)
    loaded_pyfunc = mlflow.pyfunc.load_model(downloaded)
    np.testing.assert_allclose(loaded_pyfunc.predict(frame), expected_scores, rtol=1e-10, atol=1e-10)
checkpoint('VERIFIED', model_uri=model_uri, registry_source=resolved.source)
print(json.dumps(receipt, indent=2))
PY
"$roll_python" "$roll_private/track_candidate.py" \
  "$roll_private/bundle" "$roll_app" "$roll_private/evidence"
```

Chỉ quay tiếp khi receipt là `VERIFIED`. Mở MLflow UI tại port 15000, chọn run mới:
params, validation metrics, artifacts và Registry version phải đúng receipt.
Không dùng run ID có sẵn trong model card của người khác.

Nếu upload/create timeout: giữ receipt, đọc run/version đã ghi và tra cứu server.
Không xóa receipt rồi tạo lại để có một run xanh. Đây là quy trình operator đơn
lẻ, chưa thay durable ledger/reconciliation nhiều Job trong MLFLOW-01.

Nếu dùng server `/tmp`, hãy quay phần MLflow trong cùng phiên và lưu evidence ở
host. Copy receipt không khôi phục được tracking DB/artifacts đã mất khi Pod bị
thay. Muốn dùng lâu dài phải hoàn tất persistence trước.

## 5. Chuẩn bị candidate trên volume của cluster

Bước này giữ nguyên bundle đã upload, không serialize lại pipeline. Tên thư mục
chọn theo hash toàn bundle manifest để không ghi đè candidate của lần trước:

```bash
roll_candidate_id=$("$roll_python" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest()[:16])' \
  "$roll_private/bundle/bundle-manifest.json")
roll_dest="$roll_infra/local/.local/data/models/rollout-$roll_candidate_id"
test ! -e "$roll_dest"
cp -a "$roll_private/bundle" "$roll_dest"
chmod -R a+rX "$roll_dest"
```

Chỉ tiếp tục nếu `test` và copy thành công. Không copy đè model chính hoặc sửa
metadata chỉ để đổi tên version. Registry numeric version và logical
`model_version` của MaintAI là hai định danh khác nhau; receipt liên kết chúng.
File receipt nằm cạnh evidence, không sửa serving metadata sau khi tính hash.

## 6. Image inference và thay đổi GitOps chỉ cho shadow

### 6.1. Import image local đã build thật

```bash
roll_image_id=$(docker image inspect "$roll_image" --format '{{.Id}}')
roll_serving_image="maintai-local/ml-service:rollout-${roll_image_id#sha256:}"
docker tag "$roll_image_id" "$roll_serving_image"
k3d image import --cluster maintai-local "$roll_serving_image"
```

Đây là alias local gắn với Docker image config ID đã đo, chưa phải OCI registry
manifest digest. Không chép giá trị này vào field production yêu cầu
`repository@sha256:...`. Không dùng `latest`, không nói đã publish GHCR/ECR.

Nếu muốn publisher GitHub build ML, cần PR app riêng thêm đúng ML image vào
matrix, chọn service update đúng phạm vi, lấy digest registry và xuất receipt.
Chỉ dispatch workflow sau khi PR đó được review/merge. Không chạy
`publish-and-deploy.yml --services ml-service` như thể ML đã có trong matrix.

### 6.2. Chọn đúng base branch mà Argo theo dõi

```bash
cd "$roll_infra"
k -n argocd get application maintai-local-apps \
  -o jsonpath='{.spec.source.targetRevision}{"\n"}'
gh pr list --repo chiendz11/MaintAI-gitops --state open
```

Ghi revision thật ở trên. Các PR M6 còn đang mở phải được xử lý theo nhánh nhóm
đang dùng; không mặc định chúng đã merge. Nếu Argo theo commit SHA cố định, merge
PR không tự đổi SHA đó; operator cần cập nhật revision được review trước khi sync.

Ví dụ bên dưới chỉ dùng khi Argo thực sự theo `demo/local-k3d`. Dùng GitOps
worktree mới để không trộn các chỉnh sửa M6 chưa merge ở checkout hiện tại:

```bash
roll_gitops_repo="$roll_parent/MaintAI-gitops"
git -C "$roll_gitops_repo" fetch origin
roll_base=demo/local-k3d
roll_branch="demo/model-shadow-$roll_candidate_id"
roll_gitops="$roll_parent/MaintAI-gitops-shadow-$roll_candidate_id"
git -C "$roll_gitops_repo" worktree add -b "$roll_branch" \
  "$roll_gitops" "origin/$roll_base"
```

### 6.3. Chỉ sửa cấu hình shadow, giữ nguyên phần còn lại

Chạy đoạn chuẩn bị Git diff; chưa commit/push hay gọi cluster:

```bash
"$roll_infra/.venv/bin/python" - "$roll_gitops" "$roll_dest" \
  "$roll_serving_image" "$roll_sha" "$roll_private/evidence/mlflow-receipt.json" <<'PY'
import hashlib
import json
from pathlib import Path
import sys
import yaml
root, bundle = map(Path, sys.argv[1:3])
image, source_sha, receipt_path = sys.argv[3:6]
receipt = json.loads(Path(receipt_path).read_text())
assert receipt['state'] == 'VERIFIED' and receipt['source_git_sha'] == source_sha
assert receipt['validation_gate_passed'] is True, 'Do not stage a failed candidate as an accepted shadow release'
manifest_path = bundle / 'bundle-manifest.json'
assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == receipt['bundle_manifest_sha256']
manifest = json.loads(manifest_path.read_text())
actual_files = {p.relative_to(bundle).as_posix() for p in bundle.rglob('*') if p.is_file()}
assert actual_files == set(manifest['files']) | {'bundle-manifest.json'}
for name, expected in manifest['files'].items():
    path = (bundle / name).resolve()
    assert path.is_relative_to(bundle) and hashlib.sha256(path.read_bytes()).hexdigest() == expected
assert manifest['files']['pipeline.joblib'] == receipt['pipeline_sha256']
config = root / 'environments/local/apps/kustomization.yaml'
data = yaml.safe_load(config.read_text())
assert 'generated/ml-service-shadow.yaml' in data['resources'], 'Review/enable shadow resources first'
generators = {x['name']: x for x in data['configMapGenerator']}
control = generators['ml-service-shadow-config']
env = dict(row.split('=', 1) for row in control['literals'])
env['MODEL_DIR'] = '/local/models/' + bundle.name
env['SERVICE_ROLE'] = 'shadow'
env['PRODUCER_GIT_SHA'] = source_sha
control['literals'] = [k + '=' + v for k, v in sorted(env.items())]
files = [{ 'path': '/local/models/' + bundle.name + '/' + p.relative_to(bundle).as_posix(),
           'sha256': hashlib.sha256(p.read_bytes()).hexdigest() }
         for p in sorted(bundle.rglob('*')) if p.is_file()]
generators['ml-service-shadow-artifacts']['literals'] = ['artifacts.json=' + json.dumps(files, sort_keys=True)]
entry = next(x for x in data['images'] if x['name'] == 'registry.invalid/maintai-local/ml-service-shadow')
entry['newName'], entry['newTag'] = image.rsplit(':', 1)
entry.pop('digest', None)
config.write_text(yaml.safe_dump(data, sort_keys=False))
path = root / 'environments/local/apps/generated/ml-service-shadow.yaml'
documents = list(yaml.safe_load_all(path.read_text()))
deployment = next(x for x in documents if x['kind'] == 'Deployment')
pod = deployment['spec']['template']
annotations = pod['metadata'].setdefault('annotations', {})
annotations['maintai.io/source-sha'] = source_sha
annotations['maintai.io/mlflow-run-id'] = receipt['run_id']
annotations['maintai.io/model-registry-uri'] = receipt['model_uri']
annotations['maintai.io/bundle-manifest-sha256'] = receipt['bundle_manifest_sha256']
# This path is a local manually built image, not a source-snapshot receipt from localdev.
annotations.pop('maintai.io/source-snapshot', None)
annotations['maintai.io/source-dirty'] = 'false'
container = next(x for x in pod['spec']['containers'] if x['name'] == 'ml-service-shadow')
container['imagePullPolicy'] = 'Never'
path.write_text(yaml.safe_dump_all(documents, sort_keys=False))
print('Prepared shadow-only GitOps change; review both files before committing.')
PY
git -C "$roll_gitops" diff --stat
git -C "$roll_gitops" diff -- environments/local/apps/kustomization.yaml \
  environments/local/apps/generated/ml-service-shadow.yaml
```

PyYAML có thể đổi cách xuống dòng/quote của file; review cả semantic diff. Chỉ
được thay shadow env/artifact list/image và provenance của shadow. Không đổi
champion, Worker identity, risk policy, auth, M6, HPA hoặc nhóm source locks chỉ
để tạo một PR model. Nếu base chưa có shadow/config cần thiết, dừng để chuẩn bị
PR enablement rõ phạm vi; không ghi đè cả generated folder bằng profile cũ.

### 6.4. Push branch, mở PR và kiểm tra trước merge

```bash
git -C "$roll_gitops" diff --check
git -C "$roll_gitops" add environments/local/apps/kustomization.yaml \
  environments/local/apps/generated/ml-service-shadow.yaml
git -C "$roll_gitops" commit -m "demo(ml): stage verified local candidate $roll_candidate_id as shadow"
git -C "$roll_gitops" push -u origin "$roll_branch"
cat > "$roll_private/shadow-pr.md" <<'BODY'
Deploy a newly trained, MLflow-verified candidate to the local shadow workload.
Keep champion inference and Processing model identity unchanged.

Review evidence: actual source commit, image config ID/import receipt, model
bundle checksums, MLflow run/version and validation report from this rehearsal.
Validation reuse is disclosed; approved_for_release remains false.
The model files are host-local prerequisites and are not committed to Git.

Acceptance after merge: Argo revision matches the reviewed change; shadow Ready,
real predict and model/threshold/checksum identity match; rollback restores prior
shadow configuration. Automatic request mirroring is not assumed.
BODY
gh pr create --repo chiendz11/MaintAI-gitops --head "$roll_branch" \
  --base "$roll_base" --title "demo(ml): stage local shadow candidate $roll_candidate_id" \
  --body-file "$roll_private/shadow-pr.md"
```

Đính kèm số liệu/identity thật trước review, không commit file private hoặc
credential. Source PR này không mang model bytes sang laptop khác.

Với số PR vừa tạo, ví dụ đặt `roll_pr` bằng số thật:

```bash
roll_pr=REPLACE_WITH_REAL_PR_NUMBER
gh pr view "$roll_pr" --repo chiendz11/MaintAI-gitops \
  --json headRefOid,baseRefName,mergeStateStatus,reviewDecision,url
gh pr checks "$roll_pr" --repo chiendz11/MaintAI-gitops
```

Reviewer phải xử lý hết discussion, kiểm đúng HEAD và CI/branch protection. Khi
đã đủ điều kiện và có quyết định merge, lấy lại HEAD ngay trước thao tác:

```bash
roll_head=$(gh pr view "$roll_pr" --repo chiendz11/MaintAI-gitops --json headRefOid --jq .headRefOid)
gh pr merge "$roll_pr" --repo chiendz11/MaintAI-gitops \
  --squash --match-head-commit "$roll_head"
```

Đây là lệnh người vận hành dùng trong rehearsal đã được duyệt, không phải một
bước đã thực hiện lúc viết tài liệu. Không bypass rules hoặc dùng auto-merge để
thay bằng chứng triển khai.

## 7. Argo sync và kiểm chứng model đang chạy

Mở Argo UI, chọn `maintai-local-apps`, kiểm repository/path/targetRevision.
Sau merge, Argo tự reconcile nếu auto-sync bật. Có thể Refresh rồi Sync trong UI
khi cần; không apply Deployment song song bằng kubectl. Chờ commit đã review
xuất hiện ở sync revision và Pod shadow Ready.

```bash
cd "$roll_infra"
k -n argocd get application maintai-local-apps \
  -o jsonpath='{.status.sync.revision}{" "}{.status.sync.status}{" "}{.status.health.status}{"\n"}'
k -n maintai-local rollout status deployment/ml-service-shadow --timeout=300s
k -n maintai-local get pods -l app.kubernetes.io/name=ml-service-shadow
k -n maintai-local get deployment ml-service-shadow \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
```

Manifest shadow hiện dùng `Recreate`. Có thể có khoảng shadow không sẵn sàng
khi thay Pod; đây không phải bằng chứng rolling update zero downtime. Primary
không được sửa trong PR này, nhưng vẫn phải quan sát pipeline thực tế vì các Pod
dùng chung tài nguyên laptop.

Ở terminal riêng:

```bash
k -n maintai-local port-forward --address 127.0.0.1 service/ml-service-shadow 18012:8001
```

Đọc readiness, gọi predict với contract mẫu và xem metric:

```bash
curl --fail --silent --show-error http://127.0.0.1:18012/health/ready
curl --fail --silent --show-error \
  -H 'Content-Type: application/json' \
  --data-binary "@$roll_app/contracts/v1.3/examples/http/ml/predict-request.json" \
  http://127.0.0.1:18012/api/v1/predict
curl --fail --silent --show-error http://127.0.0.1:18012/metrics \
  | rg 'maintai_ml_model_info|maintai_ml_predictions_total'
```

Kiểm response có model/preprocessor version và threshold khớp bundle; score hữu
hạn trong [0,1]. Readiness phải thật sự kiểm model loaded. Trên Grafana chỉ dùng
counter/series đã có samples; một Pod Ready chưa chứng minh đã nhận requests.
Gọi trực tiếp shadow như trên không đi vào Kafka/business alert pipeline.

**Chưa gọi cảnh này là A/B hoặc mirrored rollout.** Để thấy cùng readings chạy
cả champion và shadow phải nối Processing endpoint qua một mirror thực sự đang
hoạt động, có controller/route đúng và correlation/evaluation. File Traefik/Istio
đứng riêng hoặc counter ở dashboard không chứng minh điều đó. Không dùng độ lệch
tỷ lệ dự đoán tổng hợp làm độ chính xác nếu chưa có nhãn thật/paired evaluation.

## 8. Rollback và điều kiện trước khi thay model chính

### 8.1. Rollback shadow bằng PR revert

Lưu số merge commit của PR shadow đã merge, sau đó tạo nhánh từ base mới:

```bash
roll_merge_sha=$(gh pr view "$roll_pr" --repo chiendz11/MaintAI-gitops --json mergeCommit --jq .mergeCommit.oid)
git -C "$roll_gitops" fetch origin
git -C "$roll_gitops" switch -c "demo/rollback-shadow-$roll_candidate_id" "origin/$roll_base"
git -C "$roll_gitops" revert --no-edit "$roll_merge_sha"
git -C "$roll_gitops" push -u origin "demo/rollback-shadow-$roll_candidate_id"
gh pr create --repo chiendz11/MaintAI-gitops --base "$roll_base" \
  --head "demo/rollback-shadow-$roll_candidate_id" \
  --title 'demo(ml): restore previous shadow release' \
  --body 'Restore the previous shadow image, model path and checksums together. Keep MLflow evidence and model bundles for audit.'
```

Review/CI/merge như mục 6; sau sync kiểm lại image, config, readiness và predict.
Nếu có commit mới cùng sửa cấu hình shadow thì giải conflict theo desired state,
không force push hoặc rollback cả môi trường M6. Giữ image/model cũ cho tới khi
rollback đã được kiểm chứng. Không xóa runs, Registry versions, DB hoặc buckets.

### 8.2. Thay champion là gate riêng, chưa có một lệnh hoàn chỉnh trong localdev

Trước khi PR đổi model chính, cần đủ:

1. Quyết định cho phép dùng model trong phạm vi đã định; công khai test reuse và
   các giới hạn trong model card. Không đổi `approved_for_release` để cho qua.
2. Full model identity cho HGB: actual MLflow run, logical versions, dataset/split,
   model/preprocessor/schema hashes, real inference image digest, release ID và
   provenance có thể kiểm chứng. Helper local hiện chỉ hỗ trợ Logreg nên cần ML
   và Processing owner hoàn thiện đường này.
3. Cập nhật đồng bộ lựa chọn bundle của ML, identity mà Worker dùng và reference
   của Drift nếu bật. Chỉ đổi `MODEL_DIR` của ML có thể làm prediction không khớp
   identity mà Worker đang gắn vào outcome.
4. Kế hoạch chuyển tiếp cho request đang xử lý và replica cũ/mới: drain hoặc
   protocol đồng thời nhiều release đã được implement/kiểm chứng; thứ tự Argo
   sync đơn thuần không làm việc chuyển nhiều service thành transaction nguyên tử.
5. Nghiệm thu Processing → ML → risk → Kafka → Business → UI, kiểm source event,
   version và failure semantics; rollback cùng image/bundle/identity/reference.

Kịch bản shadow đã có đường thao tác cụ thể ở trên. Không thêm các lệnh promotion
chưa được runtime hỗ trợ rồi mô tả là đã hoàn tất triển khai champion.

## 9. Timeline và lời thoại cho video, khoảng 8–12 phút

Rehearsal có thể dài hơn nhiều vì build/install/upload. Cắt hoặc tua nhanh đoạn
chờ có chú thích; giữ lại command, kết quả thật và thời điểm chuyển bước.

| Thời gian lên hình | Cảnh | Màn hình chính |
| --- | --- | --- |
| 00:00–00:45 | Phân biệt train/tracking/deploy | Sơ đồ ở mục 1, MLflow ban đầu |
| 00:45–02:15 | Source/data và train local | Commit, split verifier, log training |
| 02:15–04:15 | Tracking và Registry | Run mới, params/metrics/artifacts, version |
| 04:15–06:15 | GitHub PR model | Diff shadow, CI, review và merge |
| 06:15–08:15 | Argo và predict shadow | Sync revision, Pod Ready, response/metrics |
| 08:15–10:15 | Rollback hoặc giải thích rollback | Revert PR, version cũ, readiness |
| 10:15–11:00 | Kết luận và giới hạn | MLflow evidence + Business UI |

### Cảnh 1 — MLflow đang trống có nghĩa gì?

> MLflow hiện chưa có run của lượt thử này. Code model nằm trong Git không có
> nghĩa kết quả thí nghiệm đã được gửi vào MLflow. Em sẽ tạo một candidate mới,
> ghi nhận kết quả và triển khai candidate riêng để thử trên Kubernetes.
>
> Có ba phần độc lập: train tạo model, MLflow lưu thí nghiệm và model Registry,
> còn GitOps chọn phiên bản để triển khai. Thành công ở một phần chưa chứng minh
> hai phần còn lại đã hoàn tất.

Nếu vẫn dùng cấu hình `/tmp`, nói thêm:

> Server local hiện dùng storage tạm cho buổi thử. Nhóm chưa trình bày đây là cấu
> hình lưu trữ bền vững. Evidence trên host được giữ riêng; muốn dùng lâu dài cần
> hoàn thiện backend và kiểm chứng việc phục hồi dữ liệu.

### Cảnh 2 — Train local từ source và data có định danh

Thao tác: hiện Git commit, kết quả `--verify-only`, sau đó log fit/validation.

> Em dùng source tại commit [đọc SHA rút gọn] và bộ AI4I có checksum/split cố định.
> Pipeline chỉ fit trên tập train. Preprocessing và các feature tương tác nằm
> trong cùng pipeline; đầu vào API vẫn là sáu feature cảm biến.
>
> Lượt này fit HGB với cấu hình đã chọn trước. Các số validation đang thấy là
> [đọc precision, recall và gate thực tế]. Threshold được tái sử dụng từ protocol;
> đây không phải một holdout mới hay phê duyệt model cho production.
>
> Model và reference được xuất vào thư mục mới. Em giữ nguyên bundle đang phục
> vụ để việc thử candidate có thể khôi phục và truy vết.

Nếu gate không đạt: vẫn có thể ghi run để phân tích, nhưng không đọc câu “model
đạt gate”. Việc đưa candidate không đạt gate vào môi trường shadow để chẩn đoán
phải được nhóm review riêng, không coi là một candidate đã được chấp nhận.

### Cảnh 3 — Upload thật vào MLflow

Thao tác: chạy uploader, chỉ mở run khi receipt đã `VERIFIED`; chọn Params,
Metrics, Artifacts và version mới trong Registry.

> Model không được upload bằng thao tác push Git. Script dùng MLflow SDK gửi
> params, metrics và artifacts tới đúng server local mà giao diện đang mở.
>
> Run ID ở đây là [đọc ID thật]. Script đã tải artifacts lại, so checksum, tải
> model từ Registry và so kết quả predict với pipeline trước khi upload.
>
> Registry version là [đọc version], liên kết tới run này. READY cho biết version
> đã được đăng ký; tag approved vẫn là false. Em chưa đổi alias champion.

Không gọi numeric Registry version là cùng loại với tên
`hgb-interactions-candidate-v1`. Không trình bày run của máy ML khác là run vừa tạo.

### Cảnh 4 — GitHub lưu quyết định triển khai

Thao tác: mở diff của PR shadow, trỏ MODEL_DIR, checksums, image và run annotation;
đọc trạng thái CI trước khi merge.

> Bundle nằm trên model volume của laptop; Git chỉ giữ đường dẫn và checksum để
> xác định đúng bytes cần nạp. PR này chọn image inference và bundle cho shadow,
> đồng thời ghi lại run/version để truy vết về kết quả train.
>
> Em giữ nguyên model chính và identity của Processing. Sau review và CI, PR mới
> được merge vào nhánh mà Argo đang theo dõi. Push branch hoặc CI xanh riêng lẻ
> chưa có nghĩa cluster đã chạy model mới.

Nếu trình bày publisher GitHub chưa hoàn thiện:

> Trong lượt local này image được build và import vào k3d. Workflow build hiện
> chưa phát hành ML image nên em không gọi đây là publish lên GHCR. Phần publisher
> cần được bổ sung trước khi chuyển sang luồng image registry hoàn toàn tự động.

### Cảnh 5 — Argo sync và model thực sự phục vụ

Thao tác: hiện sync revision/health, Pod Ready, gọi predict shadow và xem model info.

> Argo đã đọc commit [đọc commit] và đồng bộ desired state. Shadow Pod đang nạp
> bundle với các checksum đã khóa. Khi readiness pass, em gọi predict thật để
> kiểm model version, threshold và kết quả trả về.
>
> Đây là rollout của candidate riêng. Request thử đang gọi trực tiếp shadow;
> nhóm chưa dùng cảnh này để khẳng định toàn bộ readings đã được mirror hoặc
> model chính đã được thay thế.
>
> Shadow dùng Recreate nên có khoảng khởi động lại riêng. Em không sửa deployment
> chính trong PR này và vẫn quan sát Business UI để phát hiện ảnh hưởng tài nguyên.

### Cảnh 6 — Rollback có version và điều kiện promote

> Nếu phát hiện lỗi, em tạo PR revert để khôi phục image, đường dẫn model và
> checksums trước đó. Argo đồng bộ ngược lại; em vẫn phải kiểm readiness và predict.
> Lịch sử MLflow được giữ để tra cứu, không bị xóa khi rollback.
>
> Để thay model chính, cần thêm quyết định release, full identity cho Worker và
> reference tương ứng, cùng cách xử lý request đang chạy giữa hai phiên bản.
> Vì vậy demo này chứng minh chuỗi train, tracking, đăng ký và triển khai shadow;
> nó chưa chứng minh quy trình promote champion đã hoàn tất.

## 10. Bằng chứng cần lưu và tình huống phải dừng

| Bước | Evidence của lượt chạy | Không suy ra từ |
| --- | --- | --- |
| Train | Source SHA, dataset/split SHA, log fit, metrics, bundle manifest | Tên model hoặc kết quả trên máy ML khác |
| MLflow | Actual run, version, URI, receipt VERIFIED, read-back bytes/scores | UI đã mở hoặc Registry READY riêng lẻ |
| GitHub | PR URL, HEAD, CI, review, merge commit | Push branch hoặc dispatch ACK |
| Argo | Revision đúng merge, sync/health, Pod Ready | PR đã merge |
| Serving | Image thực, model/threshold/hash, predict và metrics | Pod Running |
| Rollback | Revert commit được sync, predict version cũ | Xóa Pod hoặc đổi alias MLflow |

Nếu mất MLflow, hash mismatch, sai SDK/server, mount model thiếu, image chưa
import, PR conflicts/CI fail hoặc source identity không khớp: dừng ở bước đó và
đọc đúng trạng thái. Không thay score/gate mặc định, không chạy workflow unrelated
để có dấu xanh, không reset DB/Kafka hoặc bỏ checksum validation.

## 11. Tài liệu và source đã dùng để xây kịch bản

- App: `docs/subsystems/MLFLOW_INTEGRATION_GUIDE.md` — ownership, identity,
  Tracking/Registry và retry/reconciliation.
- App: `docs/architecture/VERSIONING_AND_PROVENANCE.md` — release/model/data lineage.
- App: `ml-service/training/README.md`, `MODEL_CARD_HGB.md`,
  `ml-service/inference/HGB_HANDOFF.md` — training và giới hạn của candidate.
- App: `training/export/generate_hgb_bundle.py`, các importer/package/registry
  scripts; `ml-service/inference/Dockerfile` và serving API.
- App: `.github/workflows/publish-and-deploy.yml`, `sync-platform-locks.yml`,
  `.github/scripts/update_gitops_images.py` — phạm vi automation thực tế.
- GitOps: `docs/TRAINING.md`, `docs/LOCAL_DEVELOPMENT.md`, local generated
  MLflow/ML/shadow manifests và `environments/local/apps/kustomization.yaml`.
- Infrastructure: `localdev/demo.py` và model identity helper của Processing.
- [MLflow SDK 2.19.0](https://mlflow.org/docs/2.19.0/python_api/mlflow.client.html).

Các lệnh ở đây là nội dung runbook, không được tự thực hiện khi chỉ yêu cầu sửa
kịch bản. Giữ private evidence ngoài Git; khi thực hiện rehearsal mới ghi kết quả
thực vào bảng evidence và cập nhật lời thoại tương ứng.
