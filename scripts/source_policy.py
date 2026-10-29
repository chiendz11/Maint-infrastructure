"""Small future CI source guard; not a substitute for Terraform planning."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    locks=json.loads((ROOT/"versions/contracts.lock.json").read_text())["sha256"]
    for name,digest in locks.items():
        if hashlib.sha256((ROOT/"contracts"/name).read_bytes()).hexdigest()!=digest:raise ValueError("Contract lock mismatch")
    for path in (ROOT/"terraform").rglob("*.tf"):
        source=path.read_text()
        if "most_recent" in source and "most_recent = true" in source:raise ValueError("Floating add-on/AMI resolution is forbidden")
        if 'resource "aws_secretsmanager_secret_version"' in source:raise ValueError("Do not put application secret values in Terraform state")
    print("Source policy passed. Terraform syntax, plans, cluster behavior and deployment remain separate checks.")

if __name__=="__main__":main()
