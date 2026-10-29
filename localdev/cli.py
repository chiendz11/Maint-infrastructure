"""Explicit operators. Importing this module does not create or deploy anything."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
import uuid
from pathlib import Path

import yaml

from .common import (CONTEXT, CONTRACT, LOCAL, NAMESPACE, ROOT, apply, checkout, digest,
                     kube, private_write, read, repository_url, run, settings,
                     source_identity, validate_context, write_json, require_pinned_bases)
from .credentials import initialize, install_secrets
from .checks import verify_application_source


def pins():
    return read(ROOT / "local/versions/platform.lock.json")


def up():
    initialize()
    version = run(["k3d", "version"], capture=True)
    if not re.search(r"k3d version v" + re.escape(pins()["k3d_version"]) + r"(?:\s|$)", version):
        raise ValueError("k3d version differs from the reviewed local pin")
    client = json.loads(run(["kubectl", "version", "--client", "-o", "json"], capture=True))["clientVersion"]
    if client["major"] != "1" or not 34 <= int(client["minor"].rstrip("+")) <= 36:
        raise ValueError("kubectl must be within one minor of the local Kubernetes1.35 server")
    names = [item["name"] for item in json.loads(run(["k3d", "cluster", "list", "-o", "json"], capture=True))]
    if CONTRACT["cluster_name"] in names:
        if not (LOCAL / "cluster-owner.json").exists():
            raise ValueError("Existing maintai-local belongs to another bootstrap; migrate/export it explicitly")
        validate_context()
        run(["k3d", "cluster", "start", CONTRACT["cluster_name"]])
        return
    config = (ROOT / "local/config/k3d.yaml").read_text()
    for token, value in {"__IMAGE_K3S__": pins()["images"]["k3s"]["image"], "__LOCAL_STATE__": str(LOCAL / "state"), "__LOCAL_DATA__": str(LOCAL / "data")}.items():
        config = config.replace(token, value)
    private_write(LOCAL / "k3d.yaml", config)
    run(["k3d", "cluster", "create", "--config", str(LOCAL / "k3d.yaml"),
         "--kubeconfig-update-default=false", "--kubeconfig-switch-context=false"])
    private_write(LOCAL / "kubeconfig", run(["k3d", "kubeconfig", "get", CONTRACT["cluster_name"]], capture=True))
    write_json(LOCAL / "cluster-owner.json", {"schema_version": "1.0.0", "context": CONTEXT, "config_sha256": digest(LOCAL / "k3d.yaml")})
    validate_context()
    print("Cluster created with a private kubeconfig; no platform/app manifests applied.")


def image_receipt(component, source, dockerfile, context, extra=(), allow_dirty=False):
    sha, dirty, snapshot = source_identity(source)
    if dirty and not allow_dirty:
        raise ValueError("Source is dirty; commit it or explicitly use --allow-dirty (recorded in the receipt)")
    path = source / dockerfile
    require_pinned_bases(path.read_text(), extra)
    temporary = "maintai-local/" + component + ":build-" + snapshot[:16]
    run(["docker", "build", "--file", str(path), "--tag", temporary,
         "--label", "org.opencontainers.image.revision=" + sha,
         "--label", "maintai.io/source-snapshot=" + snapshot, *extra, str(source / context)])
    if source_identity(source) != (sha, dirty, snapshot):
        raise ValueError("Source changed during build; receipt was not created")
    identity = json.loads(run(["docker", "image", "inspect", temporary], capture=True))[0]["Id"]
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", identity):
        raise ValueError("Docker did not return an actual image identity")
    alias = "maintai-local/" + component + ":image-" + identity[7:]
    run(["docker", "tag", identity, alias])
    receipt = {"schema_version": "1.0.0", "component": component, "image": alias, "image_id": identity,
               "source_git_sha": sha, "source_dirty": dirty, "source_snapshot_sha256": snapshot,
               "dockerfile": dockerfile, "dockerfile_sha256": digest(path), "build_context": context}
    write_json(LOCAL / "receipts" / (component + ".json"), receipt)
    return receipt


def build(args):
    source = checkout("app_checkout")
    verify_application_source(source, read(ROOT / "local/versions/app-source.lock.json"))
    catalog = read(ROOT / "local/config/runtime-catalog.json")["components"]
    names = args.component or [name for name, value in catalog.items() if value["source_status"] == "implemented"]
    for name in names:
        value = catalog[name]
        extra = []
        if name in {"frontend", "simulator-ui"}:
            folder = "frontend" if name == "frontend" else "sensor-simulator-UI"
            ui = read(source / folder / "ci-images.json")
            extra = ["--build-arg", "NODE_IMAGE=" + ui["node_image"], "--build-arg", "NGINX_IMAGE=" + ui["nginx_image"]]
        if name == "mlflow":
            lock = read(source / "ml-service/mlflow/image-lock.json")
            if not lock.get("base_image") or not lock.get("compatibility_reviewed"):
                raise ValueError("MLflow server/client/base compatibility has not been reviewed in the app repo")
            extra += ["--build-arg", "MLFLOW_BASE_IMAGE=" + lock["base_image"]]
        image_receipt(name, source, value["dockerfile"], value["context"], extra, args.allow_dirty)


def build_platform(args):
    for name in ("minio", "mc", "dev-tools"):
        df, context = ("local/runtime/Dockerfile", "local/runtime") if name == "dev-tools" else ("local/images/" + name + ".Dockerfile", "local/images")
        image_receipt(name, ROOT, df, context, allow_dirty=args.allow_dirty)


def import_images(args):
    validate_context()
    names = args.component or [p.stem for p in (LOCAL / "receipts").glob("*.json")]
    if not names:
        raise ValueError("No actual image receipts; build before importing")
    for name in names:
        receipt = read(LOCAL / "receipts" / (name + ".json"))
        actual = json.loads(run(["docker", "image", "inspect", receipt["image"]], capture=True))[0]["Id"]
        if actual != receipt["image_id"]:
            raise ValueError("Local image alias no longer matches its receipt")
        run(["k3d", "image", "import", "--cluster", CONTRACT["cluster_name"], receipt["image"]])
        receipt["imported_context"] = CONTEXT
        write_json(LOCAL / "receipts" / (name + ".json"), receipt)


def prepare(args):
    receipts = {p.stem: read(p) for p in (LOCAL / "receipts").glob("*.json")}
    for value in receipts.values():
        if value.get("imported_context") != CONTEXT:
            raise ValueError("Import all selected image receipts into this cluster first")
    if args.target == "apps":
        if not args.profile:
            raise ValueError("App preparation requires a reviewed profile")
        profile = read(Path(args.profile).resolve())
        if profile["machine_count"] != settings()["machine_count"]:
            raise ValueError("Profile count differs from the explicitly provisioned registry count")
        for component in profile["components"].values():
            if not component.get("enabled"):
                continue
            for artifact in component.get("files", {}).values():
                relative = Path(artifact["path"]).relative_to("/local")
                path = (LOCAL / "data" / relative).resolve(strict=True)
                if not path.is_relative_to((LOCAL / "data").resolve()) or digest(path) != artifact["sha256"]:
                    raise ValueError("Local artifact differs from its reviewed checksum")
    bundle = LOCAL / "release-receipts.json"
    write_json(bundle, receipts)
    command = [sys.executable, "-m", "localdev.release", args.target, "--receipts", str(bundle)]
    if args.profile:
        command += ["--profile", str(Path(args.profile).resolve())]
    subprocess.run(command, cwd=checkout("gitops_checkout"), check=True)
    print("Prepared GitOps working files only. Review, commit and push them before Argo sync.")


def bootstrap_argocd():
    validate_context()
    config = settings()
    remote = repository_url(config["gitops_repository"])
    revision = config["gitops_revision"]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,100}", revision) or ".." in revision:
        raise ValueError("Invalid explicit Git revision")
    gitops = checkout("gitops_checkout")
    head = run(["git", "-C", str(gitops), "rev-parse", "HEAD"], capture=True).strip()
    if run(["git", "-C", str(gitops), "status", "--porcelain"], capture=True).strip():
        raise ValueError("GitOps changes must be committed and pushed before bootstrap")
    advertised = run(["git", "ls-remote", remote, "refs/heads/" + revision], capture=True).split()
    if not advertised or advertised[0] != head:
        raise ValueError("Remote branch does not contain the reviewed local HEAD")
    if not (gitops / "environments/local/platform/release.json").exists():
        raise ValueError("Prepare and commit real platform image receipts before bootstrap")
    install_secrets()
    upstream = pins()["argocd"]
    if not upstream.get("image_pins_complete"):
        raise ValueError("Argo installer still has unresolved upstream image identities")
    with urllib.request.urlopen(upstream["url"], timeout=30) as response:
        raw = response.read(3_000_001)
    if hashlib.sha256(raw).hexdigest() != upstream["sha256"]:
        raise ValueError("Argo installer bytes differ from the reviewed version")
    documents = list(yaml.safe_load_all(raw))

    def replace_images(value):
        if isinstance(value, dict):
            if isinstance(value.get("image"), str):
                value["image"] = upstream["images"][value["image"]]
            for item in value.values():
                replace_images(item)
        elif isinstance(value, list):
            for item in value:
                replace_images(item)

    replace_images(documents)
    apply([{"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "argocd"}}])
    kube("apply", "--server-side", "--field-manager=maintai-local-bootstrap", "-f", "-", namespace="argocd", stdin=yaml.safe_dump_all(documents))
    kube("rollout", "status", "deployment/argocd-repo-server", "--timeout=300s", namespace="argocd")
    kube("rollout", "status", "statefulset/argocd-application-controller", "--timeout=300s", namespace="argocd")
    project = {"apiVersion": "argoproj.io/v1alpha1", "kind": "AppProject", "metadata": {"name": "maintai-local", "namespace": "argocd"},
               "spec": {"sourceRepos": [remote], "destinations": [{"server": "https://kubernetes.default.svc", "namespace": NAMESPACE}],
                        "clusterResourceWhitelist": [{"group": "", "kind": "Namespace"}],
                        "namespaceResourceBlacklist": [{"group": "argoproj.io", "kind": "Application"}, {"group": "argoproj.io", "kind": "AppProject"}]}}
    applications = []
    for name, path in CONTRACT["applications"].items():
        applications.append({"apiVersion": "argoproj.io/v1alpha1", "kind": "Application", "metadata": {"name": "maintai-local-" + name, "namespace": "argocd"},
                             "spec": {"project": "maintai-local", "source": {"repoURL": remote, "targetRevision": revision, "path": path},
                                      "destination": {"server": "https://kubernetes.default.svc", "namespace": NAMESPACE},
                                      "syncPolicy": {"automated": {"prune": False, "selfHeal": True}, "syncOptions": ["FailOnSharedResource=true", "PruneLast=true"]}}})
    kube("apply", "-f", "-", namespace="argocd", stdin=yaml.safe_dump_all([project, *applications]))
    print("Argo follows three local paths in the pushed branch; production roots are not included.")


def operator_job(component, command, owner, extra=None):
    validate_context()
    receipt = read(LOCAL / "receipts" / (component + ".json"))
    if receipt.get("imported_context") != CONTEXT:
        raise ValueError("Owner image has not been imported into this cluster")
    name = "local-owner-" + uuid.uuid4().hex[:12]
    variable = "PROCESSING_DATABASE_URL" if owner == "processing" else "BUSINESS_DATABASE_URL"
    container = {"name": "operator", "image": receipt["image"], "imagePullPolicy": "Never", "command": command,
                 "env": [{"name": variable, "valueFrom": {"secretKeyRef": {"name": "local-" + owner + "-owner", "key": "url"}}}]}
    pod = {"restartPolicy": "Never", "automountServiceAccountToken": False, "containers": [container]}
    if extra:
        pod.update(extra[0]); container.update(extra[1])
    document = {"apiVersion": "batch/v1", "kind": "Job", "metadata": {"name": name, "namespace": NAMESPACE,
                "labels": {"maintai.io/owner": "explicit-local-operator"}, "annotations": {"maintai.io/image-id": receipt["image_id"], "maintai.io/source-sha": receipt["source_git_sha"]}},
                "spec": {"backoffLimit": 0, "activeDeadlineSeconds": 600, "ttlSecondsAfterFinished": 86400, "template": {"spec": pod}}}
    apply([document])
    kube("wait", "--for=condition=complete", "job/" + name, "--timeout=600s")
    print("Owner operation completed:", name, "; this is not end-to-end pipeline acceptance.")


def migrate(args):
    for owner in args.owner or ["processing", "business"]:
        component = "processing-worker" if owner == "processing" else "business-api"
        operator_job(component, ["maintai-" + owner + "-migrate", "upgrade"], owner)


def grants():
    common = "import os,psycopg;from psycopg.rows import dict_row;"
    for owner, component, code in (
        ("processing", "processing-worker", "from processing.shared.persistence.connection import grant_processing_permissions as grant; grant(c,reader_role='processing_reader',worker_role='processing_worker',relay_role='processing_relay')"),
        ("business", "business-api", "from backend.shared.persistence.permissions import grant_business_permissions as grant; grant(c,reader_role='business_reader',consumer_role='business_consumer',api_role='business_api')"),
    ):
        import_part, call = code.split("; ", 1)
        variable = "PROCESSING_DATABASE_URL" if owner == "processing" else "BUSINESS_DATABASE_URL"
        program = common + import_part + "\nwith psycopg.connect(os.environ['" + variable + "'],row_factory=dict_row) as c:\n " + call + "\n"
        operator_job(component, ["python", "-c", program], owner)


def provision():
    machines = [{"machine_id": "M-" + str(i).zfill(3), "display_name": "Simulated machine " + str(i)} for i in range(1, settings()["machine_count"] + 1)]
    name = "local-reviewed-machines"
    apply([{"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": name, "namespace": NAMESPACE}, "data": {"machines.json": json.dumps(machines)}}])
    operator_job("business-api", ["maintai-business-provision", "/review/machines.json"], "business", (
        {"volumes": [{"name": "review", "configMap": {"name": name}}]},
        {"volumeMounts": [{"name": "review", "mountPath": "/review", "readOnly": True}]},
    ))


def status():
    kube("get", "pods,svc,pvc,jobs")
    kube("get", "applications", namespace="argocd")
    print("Pod/Argo readiness is not ML correctness, Alert acceptance, load or recovery evidence.")


def smoke_kafka():
    topic = "maintai.local.smoke." + uuid.uuid4().hex[:12]
    command = ["exec", "kafka-0", "--", "/opt/kafka/bin/kafka-topics.sh", "--bootstrap-server", "kafka:9092"]
    kube(*command, "--create", "--topic", topic, "--partitions", "1", "--replication-factor", "1", "--config", "retention.ms=300000")
    message = "probe:" + uuid.uuid4().hex
    try:
        kube("exec", "-i", "kafka-0", "--", "/opt/kafka/bin/kafka-console-producer.sh", "--bootstrap-server", "kafka:9092",
             "--topic", topic, "--property", "parse.key=true", "--property", "key.separator=:", stdin=message + "\n")
        output = kube("exec", "kafka-0", "--", "/opt/kafka/bin/kafka-console-consumer.sh", "--bootstrap-server", "kafka:9092",
                      "--topic", topic, "--from-beginning", "--max-messages", "1", "--timeout-ms", "10000", capture=True)
        if message.split(":", 1)[1] not in output:
            raise ValueError("Kafka roundtrip differs")
        print("Dedicated-topic broker smoke passed. Canonical sensor topics were not modified; this is not application E2E.")
    finally:
        kube(*command, "--delete", "--topic", topic)


def submit_training(args):
    validate_context()
    spec = read(Path(args.manifest).resolve())
    receipt = read(LOCAL / "receipts/training.json")
    if receipt.get("imported_context") != CONTEXT or spec.get("runtime_reviewed") is not True:
        raise ValueError("Training needs an imported owner-reviewed image")
    if not spec.get("approved_dataset_version") or not re.fullmatch(r"[0-9a-f]{64}", spec.get("dataset_manifest_sha256", "")):
        raise ValueError("Training requires an approved, versioned dataset manifest")
    manifest = spec.get("approved_dataset_manifest", {})
    if (manifest.get("bucket") != "maintai-approved" or not manifest.get("key")
            or not manifest.get("version_id") or manifest.get("sha256") != spec["dataset_manifest_sha256"]):
        raise ValueError("Training must identify the approved manifest by bucket/key/VersionId/SHA256")
    command = spec.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(s, str) and s for s in command):
        raise ValueError("Supply the real training entrypoint; no synthetic trainer is supplied")
    for key in spec.get("env", {}):
        if re.search(r"PASSWORD|SECRET|TOKEN|API_KEY", key):
            raise ValueError("Training credentials belong in the scoped Kubernetes Secret")
    name = "local-training-" + uuid.uuid4().hex[:12]
    job = {"apiVersion": "batch/v1", "kind": "Job", "metadata": {"name": name, "namespace": NAMESPACE,
        "annotations": {"maintai.io/approved-dataset-version": spec["approved_dataset_version"], "maintai.io/dataset-manifest-sha256": spec["dataset_manifest_sha256"], "maintai.io/source-sha": receipt["source_git_sha"]}},
        "spec": {"backoffLimit": 0, "activeDeadlineSeconds": 3600, "ttlSecondsAfterFinished": 86400, "template": {"spec": {
            "restartPolicy": "Never", "automountServiceAccountToken": False,
            "containers": [{"name": "training", "image": receipt["image"], "imagePullPolicy": "Never", "command": command,
                "envFrom": [{"secretRef": {"name": "local-training-env"}}],
                "env": [{"name": "MLFLOW_TRACKING_URI", "value": "http://mlflow:5000"},
                        {"name": "APPROVED_DATASET_MANIFEST", "value": json.dumps(manifest, sort_keys=True)}] + [{"name": k, "value": v} for k, v in spec.get("env", {}).items()],
                "resources": {"requests": {"cpu": "500m", "memory": "512Mi"}, "limits": {"cpu": "2", "memory": "2Gi"}}}]
        }}}}
    apply([job])
    print("Submitted approved training Job:", name, "; model promotion remains a reviewed release operation.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="MaintAI local k3d bootstrap; no Terraform/AWS execution")
    sub = parser.add_subparsers(dest="operation", required=True)
    for name in ("init", "up", "secrets", "bootstrap-argocd", "status", "stop", "start", "grants", "provision", "smoke-kafka"):
        sub.add_parser(name)
    for name in ("build", "build-platform"):
        command = sub.add_parser(name); command.add_argument("--allow-dirty", action="store_true")
        if name == "build": command.add_argument("--component", action="append", choices=list(read(ROOT / "local/config/runtime-catalog.json")["components"]))
    command = sub.add_parser("import-images"); command.add_argument("--component", action="append")
    command = sub.add_parser("prepare"); command.add_argument("target", choices=["platform", "apps"]); command.add_argument("--profile")
    command = sub.add_parser("migrate"); command.add_argument("--owner", action="append", choices=["processing", "business"])
    command = sub.add_parser("activate-ordering"); command.add_argument("--legacy-writers-drained", action="store_true", required=True)
    command = sub.add_parser("delete"); command.add_argument("--confirm-delete-cluster", action="store_true", required=True)
    command = sub.add_parser("forward"); command.add_argument("service", choices=["argocd", "kafka", "postgres"])
    command = sub.add_parser("submit-training"); command.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    try:
        if args.operation == "init":
            initialize()
            print("Private local settings initialized; existing credentials preserved.")
        elif args.operation == "up": up()
        elif args.operation == "secrets": install_secrets()
        elif args.operation == "build": build(args)
        elif args.operation == "build-platform": build_platform(args)
        elif args.operation == "import-images": import_images(args)
        elif args.operation == "prepare": prepare(args)
        elif args.operation == "bootstrap-argocd": bootstrap_argocd()
        elif args.operation == "migrate": migrate(args)
        elif args.operation == "grants": grants()
        elif args.operation == "provision": provision()
        elif args.operation == "activate-ordering": operator_job("processing-worker", ["maintai-processing-migrate", "activate-ordering", "--legacy-writers-drained"], "processing")
        elif args.operation == "status": status()
        elif args.operation == "smoke-kafka": smoke_kafka()
        elif args.operation == "submit-training": submit_training(args)
        elif args.operation in {"stop", "start", "delete"}:
            validate_context(); run(["k3d", "cluster", args.operation, CONTRACT["cluster_name"]])
        elif args.operation == "forward":
            value = {"argocd": ("argocd-server", "18443:443", "argocd"), "kafka": ("kafka", "19092:19092", NAMESPACE), "postgres": ("postgres", "15432:5432", NAMESPACE)}[args.service]
            kube("port-forward", "--address=127.0.0.1", "service/" + value[0], value[1], namespace=value[2])
        return 0
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError):
        print("Local operation failed; no automatic rollback or success fallback. Inspect private local state/operator logs.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
