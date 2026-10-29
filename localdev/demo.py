"""Explicit local identity and knowledge-owner operations; no synthetic success."""

import json
import re
import subprocess
import sys

import yaml

from .common import (
    CONTEXT,
    LOCAL,
    ROOT,
    apply,
    checkout,
    digest,
    kube,
    read,
    run,
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
