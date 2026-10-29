"""Entrypoint for the local-only bridge and expiring service token files."""

import argparse
import hashlib
import json
import signal
import threading
import time
from pathlib import Path

from bridge import serve
from oauth import Tokens, refresh_forever


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["serve", "tokens-once", "verify-files"])
    parser.add_argument("--config", default="/config/bridge.json")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    if args.operation == "verify-files":
        for artifact in config:
            path = Path(artifact["path"])
            if not str(path).startswith("/local/") or ".." in path.parts:
                raise ValueError("Artifact path must be inside the read-only local mount")
            checksum = hashlib.sha256()
            with path.open("rb") as source:
                while chunk := source.read(1048576):
                    checksum.update(chunk)
            if checksum.hexdigest() != artifact["sha256"]:
                raise ValueError("Local artifact differs from its reviewed checksum")
        return
    if config.get("environment") != "local-k3d":
        raise ValueError("Development adapter requires an explicit local-k3d profile")
    tokens = Tokens(config.get("oauth", {}))
    directory = config.get("token_directory", "/tokens")
    if args.operation == "tokens-once":
        deadline = time.monotonic() + 180
        while True:
            try:
                tokens.write(directory)
                return
            except Exception:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Local token initialization unavailable") from None
                time.sleep(2)
    stopped = threading.Event()
    for event in (signal.SIGTERM, signal.SIGINT):
        signal.signal(event, lambda *_: stopped.set())
    if config.get("oauth"):
        threading.Thread(target=refresh_forever, args=(tokens, directory, stopped), daemon=True).start()
    serve(config, tokens, stopped)


if __name__ == "__main__":
    main()
