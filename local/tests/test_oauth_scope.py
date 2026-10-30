"""Unspecified scope is omitted; a caller cannot accidentally request an empty scope."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs

path = Path(__file__).resolve().parents[1] / "runtime/oauth.py"
spec = importlib.util.spec_from_file_location("demo_oauth", path)
oauth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oauth)


class OAuthScope(unittest.TestCase):
    def request(self, scope):
        with tempfile.TemporaryDirectory() as folder:
            secret = Path(folder) / "secret"
            secret.write_text("fixture-not-a-real-secret")
            configuration = {"processing": {"token_url": "http://keycloak:8080/realms/maintai/protocol/openid-connect/token", "client_id": "maintai-processing", "secret_file": str(secret)}}
            if scope is not None:
                configuration["processing"]["scope"] = scope
            response = MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps({"access_token": "fixture-token", "expires_in": 300, "token_type": "Bearer"}).encode()
            opener = MagicMock()
            opener.open.return_value = response
            with patch.object(oauth.urllib.request, "build_opener", return_value=opener):
                self.assertEqual(oauth.Tokens(configuration).get("processing"), "fixture-token")
            return parse_qs(opener.open.call_args.args[0].data.decode(), keep_blank_values=True)

    def test_absent_and_empty_scope_are_omitted(self):
        for scope in (None, ""):
            self.assertNotIn("scope", self.request(scope))

    def test_explicit_scope_is_preserved(self):
        self.assertEqual(self.request("sensor:write")["scope"], ["sensor:write"])
