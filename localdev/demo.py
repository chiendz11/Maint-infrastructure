"""Explicit local identity and knowledge-owner operations; no synthetic success."""

import json
from pathlib import Path
import re
import subprocess
import sys

import yaml

from .common import (
    CONTEXT,
    LOCAL,
    NAMESPACE,
    ROOT,
    apply,
    checkout,
    digest,
    kube,
    read,
    run,
    validate_context,
    write_json,
)
from .checks import verify_application_source


def serving_reference(receipt, inspection):
    if inspection["Id"] != receipt["image_id"]:
        raise ValueError("Serving image no longer matches its receipt")
    references = [
        value
        for value in inspection.get("RepoDigests", [])
        if re.fullmatch(r"maintai-local/ml-service@sha256:[0-9a-f]{64}", value)
    ]
    if len(references) != 1:
        raise ValueError(
            "A real local serving OCI RepoDigest is required; config ID is insufficient"
        )
    descriptor = inspection.get("Descriptor", {}).get("digest")
    if descriptor and references[0].split("@", 1)[1] != descriptor:
        raise ValueError("Serving OCI descriptor differs from its repository digest")
    return references[0]


def model_identity():
    app = checkout("app_checkout")
    lock = read(ROOT / "local/versions/app-source.lock.json")
    verify_application_source(app, lock)
    receipts = {
        name: read(LOCAL / "receipts" / (name + ".json"))
        for name in ("ml-service", "processing-worker")
    }
    for receipt in receipts.values():
        if (
            receipt["source_git_sha"] != lock["source_git_sha"]
            or receipt["source_dirty"]
        ):
            raise ValueError(
                "Build both ML and Worker images from the pinned clean application source"
            )
        inspection = json.loads(
            run(["docker", "image", "inspect", receipt["image"]], capture=True)
        )[0]
        if inspection["Id"] != receipt["image_id"]:
            raise ValueError("Image receipt no longer matches the local Docker store")
    inspected = json.loads(
        run(
            ["docker", "image", "inspect", receipts["ml-service"]["image"]],
            capture=True,
        )
    )[0]
    reference = serving_reference(receipts["ml-service"], inspected)
    split = (
        app
        / "ml-service/training/data_preparation/splits/ai4i-stratified-v1-seed42.json"
    )
    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--entrypoint",
        "python",
        "--mount",
        "type=bind,src=" + str(LOCAL / "data") + ",dst=/local,readonly",
        "--mount",
        "type=bind,src=" + str(split) + ",dst=/review/split.json,readonly",
        receipts["processing-worker"]["image"],
        "-m",
        "processing.shared.inference_client.local_identity",
        "--bundle",
        "/local/models/logreg-baseline-v0",
        "--dataset",
        "/local/datasets/ai4i2020.csv",
        "--split",
        "/review/split.json",
        "--feature-schema",
        "/app/http-contracts/features.schema.json",
        "--image-reference",
        reference,
        "--source-sha",
        lock["source_git_sha"],
    ]
    result = json.loads(run(command, capture=True))
    result["evidence"]["image_receipts"] = receipts
    identity_path = LOCAL / "data/fixtures/model-identity.json"
    write_json(identity_path, result["identity"])
    write_json(
        LOCAL / "data/fixtures/model-identity.provenance.json", result["evidence"]
    )
    # Artifacts are not credentials; allow the non-root Worker to read them.
    identity_path.chmod(0o644)
    print("Verified local model identity written; sha256=" + digest(identity_path))
    print("No MLflow run, approved training manifest or quality approval is claimed.")


def prepare_rag():
    app = checkout("app_checkout")
    verify_application_source(app, read(ROOT / "local/versions/app-source.lock.json"))
    receipt_path = LOCAL / "receipts/rag-service.json"
    receipt = read(receipt_path)
    if receipt.get("imported_context") != CONTEXT:
        raise ValueError("Import the real RAG image into the owned cluster first")
    kube("get", "pvc", "local-rag-embedding-cache", capture=True)
    # GitOps authors the Job; infrastructure only executes the explicit owner op.
    job_file = LOCAL / "rag-prepare-job.yaml"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "localdev.rag_job",
            "--receipt",
            str(receipt_path),
            "--output",
            str(job_file),
        ],
        cwd=checkout("gitops_checkout"),
        env={**os.environ, "PYTHONPATH": "scripts"},
        check=True,
    )
    job = yaml.safe_load(job_file.read_text())
    job_file.chmod(0o600)
    apply([job])
    name = job["metadata"]["name"]
    print("Waiting for explicit knowledge-owner Job:", name, flush=True)
    kube("wait", "--for=condition=complete", "job/" + name, "--timeout=1800s")
    logs = kube("logs", "job/" + name, capture=True)
    # Keep raw owner logs private; publish only the machine-readable safe result.
    from .common import private_write

    private_write(LOCAL / "rag-prepare.log", logs)
    report = next(
        (
            json.loads(line)
            for line in reversed(logs.splitlines())
            if line.startswith('{"schema_version":')
            and '"groq_generation_tested"' in line
        ),
        None,
    )
    if report is None:
        raise ValueError("Knowledge owner completed without a verification report")
    report["job_name"] = name
    report["source_git_sha"] = receipt["source_git_sha"]
    report["image_id"] = receipt["image_id"]
    write_json(LOCAL / "rag-knowledge-receipt.json", report)
    print(
        "Knowledge schema/cache/ingestion/retrieval verified; report: local/.local/rag-knowledge-receipt.json"
    )


def _free_loopback_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def seed_approved_dataset(version="ai4i2020-local-demo-v1", prefix="hgb-interactions", dataset=None):
    """Upload a verified dataset CSV and approved manifest into MinIO maintai-approved."""
    import hashlib
    import time
    import boto3

    validate_context()
    source = Path(dataset).resolve() if dataset else checkout("app_checkout") / "sensor/data/ai4i2020.csv"
    if not source.is_file():
        raise FileNotFoundError(f"Dataset CSV not found: {source}")
    credentials = read(LOCAL / "credentials.json")
    csv_bytes = source.read_bytes()
    csv_sha = hashlib.sha256(csv_bytes).hexdigest()
    port = _free_loopback_port()
    forward = subprocess.Popen(
        [
            "kubectl", "--kubeconfig", str(LOCAL / "kubeconfig"), "--context", CONTEXT,
            "--namespace", NAMESPACE, "port-forward", "--address=127.0.0.1",
            "service/minio", f"{port}:9000",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        endpoint = f"http://127.0.0.1:{port}"
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id="maintai-root",
            aws_secret_access_key=credentials["minio_root_password"],
            region_name="us-east-1",
        )
        for _ in range(30):
            if forward.poll() is not None:
                raise RuntimeError(f"MinIO port-forward exited early: {forward.stderr.read()}")
            try:
                client.head_bucket(Bucket="maintai-approved")
                break
            except Exception:
                time.sleep(0.3)
        else:
            raise TimeoutError("Timed out waiting for MinIO port-forward")

        csv_key = f"datasets/approved/{version}.csv"
        csv_put = client.put_object(Bucket="maintai-approved", Key=csv_key, Body=csv_bytes, ContentType="text/csv")
        csv_vid = csv_put["VersionId"]
        manifest = {
            "schema_version": "1.0.0",
            "dataset_version": version,
            "model_version_prefix": prefix,
            "model_family": "hgb_interactions",
            "split_seed": 42,
            "dataset": {
                "bucket": "maintai-approved",
                "key": csv_key,
                "version_id": csv_vid,
                "sha256": csv_sha,
            },
        }
        manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
        manifest_key = f"datasets/approved/{version}.manifest.json"
        manifest_put = client.put_object(
            Bucket="maintai-approved", Key=manifest_key, Body=manifest_bytes, ContentType="application/json"
        )
        summary = {
            "approved_dataset_version": version,
            "dataset_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "approved_dataset_manifest": {
                "bucket": "maintai-approved",
                "key": manifest_key,
                "version_id": manifest_put["VersionId"],
                "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            },
        }
        print(json.dumps(summary, indent=2))
        return summary
    finally:
        forward.terminate()
        forward.wait(timeout=5)


def sync_model_versions():
    """Read live MinIO VersionIds for local champion/shadow models and publish to LocalStack SSM."""
    import time
    import boto3
    from .secret_store import build_model_version_parameters, put_local_ssm_parameters

    validate_context()
    credentials = read(LOCAL / "credentials.json")
    port = _free_loopback_port()
    forward = subprocess.Popen(
        [
            "kubectl", "--kubeconfig", str(LOCAL / "kubeconfig"), "--context", CONTEXT,
            "--namespace", NAMESPACE, "port-forward", "--address=127.0.0.1",
            "service/minio", f"{port}:9000",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        client = boto3.client(
            "s3",
            endpoint_url=f"http://127.0.0.1:{port}",
            aws_access_key_id="maintai-root",
            aws_secret_access_key=credentials["minio_root_password"],
            region_name="us-east-1",
        )
        for _ in range(30):
            if forward.poll() is not None:
                raise RuntimeError(f"MinIO port-forward exited early: {forward.stderr.read()}")
            try:
                client.head_bucket(Bucket="maintai-models")
                break
            except Exception:
                time.sleep(0.3)
        else:
            raise TimeoutError("Timed out waiting for MinIO port-forward")

        files = {
            "pipeline": "pipeline.joblib",
            "metadata": "metadata.json",
            "evaluation": "evaluation.json",
            "drift_reference": "drift_reference.json",
        }
        champion = {
            field: client.head_object(Bucket="maintai-models", Key=f"models/logreg-baseline-v0/{filename}")["VersionId"]
            for field, filename in files.items()
        }
        shadow = {
            field: client.head_object(Bucket="maintai-models", Key=f"models/hgb-interactions-candidate-v1/{filename}")["VersionId"]
            for field, filename in files.items()
        }
        parameters = build_model_version_parameters(champion, shadow)
        put_local_ssm_parameters(parameters)
        print("Local model VersionIds synced to LocalStack SSM Parameter Store.")
        return parameters
    finally:
        forward.terminate()
        forward.wait(timeout=5)
