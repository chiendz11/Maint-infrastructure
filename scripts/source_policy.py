from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    terraform_root = ROOT / "terraform"
    tf_files = sorted(terraform_root.rglob("*.tf"))
    if not tf_files:
        raise ValueError("No Terraform source files found under terraform/")

    for tf_path in tf_files:
        text = tf_path.read_text(encoding="utf-8")
        rel = tf_path.relative_to(ROOT)
        if "most_recent = true" in text or "most_recent=true" in text:
            raise ValueError(f"Mutable most_recent data lookup forbidden: {rel}")
        if 'resource "aws_secretsmanager_secret_version"' in text:
            raise ValueError(f"Secret versions must not be managed in Terraform state: {rel}")
        if re.search(r'resource\s+"aws_ssm_parameter"[^{]*\{[^}]*type\s*=\s*"SecureString"', text, re.S):
            raise ValueError(f"SSM SecureString values must not be managed in Terraform state: {rel}")

    print("Source policy passed. Terraform syntax, plans, cluster behavior and deployment remain separate checks.")


if __name__ == "__main__":
    main()
