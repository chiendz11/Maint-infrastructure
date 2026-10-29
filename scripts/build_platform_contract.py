from __future__ import annotations

import argparse
import json
from pathlib import Path
import jsonschema

ROOT=Path(__file__).resolve().parents[1]


def build(outputs: dict) -> dict:
    value=outputs["platform_contract"]["value"]
    schema=json.loads((ROOT/"contracts/platform-contract-v2.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(value)
    # Never return unselected Terraform outputs, sensitive values, kubeconfig, or backend contents.
    return value

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--input",required=True);parser.add_argument("--output",required=True);args=parser.parse_args()
    Path(args.output).write_text(json.dumps(build(json.loads(Path(args.input).read_text())),indent=2)+"\n")
