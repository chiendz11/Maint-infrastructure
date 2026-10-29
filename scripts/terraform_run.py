"""Explicit workflow runner. It is not invoked by initial code generation."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
ROOTS={"bootstrap","domain","platform","argocd"}


def run(*args: str, capture: bool=False):
    if capture:return subprocess.check_output(list(args),cwd=ROOT,text=True)
    subprocess.run(list(args),cwd=ROOT,check=True)


def initialize(root: str) -> None:
    if root not in ROOTS:raise ValueError("Unknown Terraform root")
    for name in ["TF_STATE_BUCKET","TF_STATE_KMS_KEY_ARN","AWS_REGION"]:
        if not os.environ.get(name):raise ValueError("Missing workflow configuration: "+name)
    if root == "bootstrap":
        backend = ROOT / "terraform/bootstrap/backend.tf"
        if not backend.exists():backend.write_text((ROOT / "terraform/bootstrap/backend.tf.example").read_text())
    run("terraform",f"-chdir=terraform/{root}","init","-input=false","-lockfile=readonly","-backend-config=bucket="+os.environ["TF_STATE_BUCKET"],"-backend-config=region="+os.environ["AWS_REGION"],"-backend-config=kms_key_id="+os.environ["TF_STATE_KMS_KEY_ARN"])


def main() -> None:
    parser=argparse.ArgumentParser();parser.add_argument("operation",choices=["plan","apply"]);args=parser.parse_args()
    root=os.environ["TF_ROOT"]
    if args.operation=="apply":
        expected=os.environ.get("EXPECTED_MAIN_SHA","")
        if not re.fullmatch(r"[0-9a-f]{40}",expected):raise ValueError("Provide exact reviewed main SHA")
        head=run("git","rev-parse","HEAD",capture=True).strip()
        remote=run("git","ls-remote","origin","refs/heads/main",capture=True).split()[0]
        if head!=expected or remote!=expected:raise ValueError("Reviewed main SHA is stale")
    values=json.loads(os.environ["TFVARS_JSON"])
    if any(re.search(r"password|private_key|access_key|secret_value",key,re.I) for key in values):
        raise ValueError("Terraform variables must reference secrets rather than contain secret values")
    initialize(root)
    with tempfile.TemporaryDirectory() as temporary:
        variables=Path(temporary)/"input.tfvars.json";variables.write_text(json.dumps(values));variables.chmod(0o600)
        saved=Path(temporary)/"reviewed.tfplan"
        run("terraform",f"-chdir=terraform/{root}","plan","-input=false","-lock-timeout=5m","-var-file="+str(variables),"-out="+str(saved))
        if args.operation=="apply":run("terraform",f"-chdir=terraform/{root}","apply","-input=false","-auto-approve",str(saved))

if __name__=="__main__":main()
