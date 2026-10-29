"""Client credentials for a fixed local Keycloak, never an authentication bypass."""

import json
import os
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path


class Tokens:
    def __init__(self, configuration):
        self.configuration = configuration
        self.values = {}
        self.lock = threading.Lock()

    def get(self, name):
        with self.lock:
            token, expiry = self.values.get(name, ("", 0))
            if time.time() < expiry - 45:
                return token
            spec = self.configuration[name]
            # Only the local service endpoint is permitted, no arbitrary credential sink.
            endpoint = spec["token_url"]
            parsed = urllib.parse.urlsplit(endpoint)
            if parsed.scheme != "http" or parsed.hostname not in {
                "keycloak", "keycloak.maintai-local.svc.cluster.local"
            } or parsed.port not in {None, 8080} or parsed.query or parsed.fragment:
                raise ValueError("Unexpected local identity endpoint")
            secret = Path(spec["secret_file"]).read_text().strip()
            data = urllib.parse.urlencode({
                "grant_type": "client_credentials", "client_id": spec["client_id"],
                "client_secret": secret, "scope": spec.get("scope", ""),
            }).encode()
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(urllib.request.Request(endpoint, data=data), timeout=5) as response:
                raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError("Token response exceeds bound")
            value = json.loads(raw)
            ttl = float(value["expires_in"])
            token = value["access_token"]
            if (value.get("token_type", "").lower() != "bearer" or not 60 <= ttl <= 3600
                or not isinstance(token, str) or not token or len(token) > 16384
                or any(c.isspace() for c in token)):
                raise ValueError("Invalid token response")
            self.values[name] = token, time.time() + ttl
            return token

    def write(self, directory):
        root = Path(directory)
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        for name in self.configuration:
            token = self.get(name)
            fd, temporary = tempfile.mkstemp(dir=root)
            try:
                with os.fdopen(fd, "w") as stream:
                    stream.write(token)
                os.replace(temporary, root / (name + ".jwt"))
            finally:
                Path(temporary).unlink(missing_ok=True)


def refresh_forever(tokens, directory, stopped):
    while not stopped.is_set():
        try:
            tokens.write(directory)
        except Exception:
            # No exception text: HTTP errors may contain credential-bearing URLs.
            print("local token refresh unavailable", flush=True)
            for name, (_, expiry) in list(tokens.values.items()):
                if time.time() >= expiry:
                    (Path(directory) / (name + ".jwt")).unlink(missing_ok=True)
        stopped.wait(15)
