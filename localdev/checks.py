"""Future offline CI checks. This module never calls Docker, kubectl or AWS."""

import argparse
import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path

from .common import ROOT, read


def verify_application_source(app, lock):
    """Verify both the reviewed Git revision and its selected interface bytes."""
    if lock.get("schema_version") != "1.0.0" or lock.get("source_repository") != "chiendz11/MaintAI":
        raise ValueError("Unexpected application source lock identity")
    sha = lock.get("source_git_sha", "")
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha) or not lock.get("files"):
        raise ValueError("Application source lock requires a real revision and file hashes")
    actual = subprocess.check_output(["git", "-C", str(app), "rev-parse", "HEAD"], text=True).strip()
    if actual != sha:
        raise ValueError("Application checkout HEAD differs from the reviewed source lock")
    for name, expected in lock["files"].items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError("Invalid application source lock entry: " + name)
        if hashlib.sha256((app / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("Application interface drift requires review: " + name)


def check(app=None, companion=None):
    for path in [*(ROOT / "localdev").glob("*.py"), *(ROOT / "local/runtime").glob("*.py")]:
        ast.parse(path.read_text(), filename=str(path))
    for filename in ("local-contracts.lock.json", "local-production-baseline.lock.json"):
        lock = read(ROOT / "versions" / filename)["sha256"]
        for name, expected in lock.items():
            path = ROOT / "contracts/local" / name if filename == "local-contracts.lock.json" else ROOT / name
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError("Protected local contract or production source changed: " + name)
    source = (ROOT / "localdev/cli.py").read_text()
    if "use-context" in source or "terraform" in source.lower().replace("no terraform/aws execution", ""):
        raise ValueError("Local operator must not change current context or call Terraform")
    if app:
        verify_application_source(app, read(ROOT / "local/versions/app-source.lock.json"))
    if companion:
        pairs = [("local/versions/app-source.lock.json", "config/local/app-source.lock.json"),
                 ("local/config/contract.json", "config/local/contract.json"), ("local/config/runtime-catalog.json", "config/local/runtime-catalog.json"),
                 ("local/config/buckets.json", "config/local/buckets.json"), ("local/versions/platform.lock.json", "config/local/platform.lock.json")]
        pairs += [("contracts/local/" + p.name, "contracts/local/" + p.name) for p in (ROOT / "contracts/local").glob("*.json")]
        for left, right in pairs:
            if (ROOT / left).read_bytes() != (companion / right).read_bytes():
                raise ValueError("Cross-repository local contract differs: " + left)
    print("Offline source/contract policy passed; no build, cluster, runtime or E2E validation.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-root", type=Path)
    parser.add_argument("--gitops-root", type=Path)
    args = parser.parse_args()
    check(args.app_root, args.gitops_root)


if __name__ == "__main__":
    main()
