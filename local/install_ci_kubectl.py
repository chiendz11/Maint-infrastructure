"""Install one checksum-pinned kubectl into a CI temporary directory, no kubeconfig."""

import hashlib
import json
import os
import urllib.request
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    pin = json.loads((root / "local/versions/platform.lock.json").read_text())["kubectl"]
    with urllib.request.urlopen(pin["linux_amd64_url"], timeout=60) as response:
        binary = response.read(100_000_001)
    if len(binary) > 100_000_000 or hashlib.sha256(binary).hexdigest() != pin["sha256"]:
        raise ValueError("kubectl bytes differ from the reviewed official checksum")
    folder = Path(os.environ["RUNNER_TEMP"]) / "maintai-ci-bin"
    folder.mkdir(exist_ok=True)
    executable = folder / "kubectl"
    executable.write_bytes(binary)
    executable.chmod(0o755)
    with open(os.environ["GITHUB_PATH"], "a") as paths:
        paths.write(str(folder) + "\n")


if __name__ == "__main__":
    main()
