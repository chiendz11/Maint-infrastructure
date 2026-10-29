"""Private state and argument-array subprocesses for one local cluster."""

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "local/.local"
CONTRACT = json.loads((ROOT / "local/config/contract.json").read_text())
CONTEXT, NAMESPACE = CONTRACT["context"], CONTRACT["namespace"]


def read(path):
    return json.loads(Path(path).read_text())


def private_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_json(path, value):
    private_write(path, json.dumps(value, indent=2) + "\n")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(args, *, capture=False, stdin=None):
    result = subprocess.run(args, input=stdin, text=True, capture_output=capture, check=True)
    return result.stdout if capture else None


def settings():
    value = read(LOCAL / "settings.json")
    if value.get("schema_version") != "1.0.0" or type(value.get("machine_count")) is not int or not 1 <= value["machine_count"] <= 100:
        raise ValueError("Invalid explicit local settings")
    return value


def checkout(key):
    return (ROOT / settings()[key]).resolve(strict=True)


def validate_context():
    config = yaml.safe_load((LOCAL / "kubeconfig").read_text())
    contexts = {item["name"]: item["context"] for item in config["contexts"]}
    clusters = {item["name"]: item["cluster"] for item in config["clusters"]}
    selected = contexts[CONTEXT]
    if clusters[selected["cluster"]]["server"] != CONTRACT["api_server"]:
        raise ValueError("Private kubeconfig must target the fixed loopback API")
    if not (LOCAL / "cluster-owner.json").is_file():
        raise ValueError("This bootstrap does not own the existing cluster")
    marker = read(LOCAL / "cluster-owner.json")
    if marker.get("context") != CONTEXT or marker.get("config_sha256") != digest(LOCAL / "k3d.yaml"):
        raise ValueError("Local cluster ownership/config identity differs; review the cutover explicitly")


def kube(*args, capture=False, stdin=None, namespace=NAMESPACE):
    validate_context()
    return run(["kubectl", "--kubeconfig", str(LOCAL / "kubeconfig"), "--context", CONTEXT,
                "--namespace", namespace, *args], capture=capture, stdin=stdin)


def apply(documents):
    # Secret values go through stdin, never argv, logs or committed files.
    kube("apply", "-f", "-", stdin=yaml.safe_dump_all(documents, sort_keys=False))


def repository_url(value):
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or not parsed.path.endswith(".git")):
        raise ValueError("Use an HTTPS Git repository URL without embedded credentials")
    return value


def source_identity(root):
    sha = run(["git", "-C", str(root), "rev-parse", "HEAD"], capture=True).strip()
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha):
        raise ValueError("Source has no valid Git revision")
    dirty = bool(run(["git", "-C", str(root), "status", "--porcelain"], capture=True).strip())
    names = run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"], capture=True)
    fingerprint = hashlib.sha256()
    for name in sorted(set(names.split("\0")) - {""}):
        path = root / name
        if path.is_symlink():
            payload = os.readlink(path).encode()
        elif path.is_file():
            payload = path.read_bytes()
        else:
            payload = b"<deleted>"
        fingerprint.update(name.encode() + b"\0" + hashlib.sha256(payload).digest())
    return sha, dirty, fingerprint.hexdigest()


def require_pinned_bases(source, extra=()):
    arguments = dict(re.findall(r"^ARG\s+([A-Za-z_][A-Za-z_0-9]*)=([^\r\n]+)$", source, re.MULTILINE))
    for index, value in enumerate(extra):
        if value == "--build-arg" and index + 1 < len(extra):
            key, content = extra[index + 1].split("=", 1)
            arguments[key] = content
    stages = set()
    found = False
    for line in source.splitlines():
        words = line.strip().split()
        if not words or words[0].upper() != "FROM":
            continue
        found = True
        index = 2 if len(words) > 1 and words[1].startswith("--platform=") else 1
        image = words[index]
        image = re.sub(r"\$\{([A-Za-z_][A-Za-z_0-9]*)\}", lambda match: arguments.get(match[1], "UNCONFIGURED"), image)
        if image not in stages and image != "scratch" and not re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", image):
            raise ValueError("Owner Dockerfile/base arguments require immutable image digests")
        if len(words) > index + 2 and words[index + 1].upper() == "AS":
            stages.add(words[index + 2])
    if not found:
        raise ValueError("Dockerfile is a placeholder; supply the owner's implementation")
