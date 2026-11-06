import base64
import importlib.util
import json
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import Mock, patch

from localdev.history import cursor, new_keys
from localdev.cli import local_autoscaling_options

path = Path(__file__).resolve().parents[1] / "runtime/bridge.py"
spec = importlib.util.spec_from_file_location("history_bridge", path)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class HistoryKeys(unittest.TestCase):
    def test_history_rollout_preserves_hpa_replica_ownership(self):
        value = local_autoscaling_options()
        rules = value["ignoreDifferences"]
        self.assertIn("processing-worker", {row["name"] for row in rules})
        self.assertNotIn("storage-consumer", {row["name"] for row in rules})
        self.assertTrue(all(row["jsonPointers"] == ["/spec/replicas"] for row in rules))
        self.assertIn("RespectIgnoreDifferences=true", value["syncPolicy"]["syncOptions"])
        self.assertFalse(value["syncPolicy"]["automated"]["prune"])

    def test_separate_cursor_keys_and_public_only_jwks(self):
        value = new_keys()
        self.assertNotEqual(value["business_cursor"], value["processing_cursor"])
        self.assertEqual(len(base64.b64decode(value["business_cursor"])), 32)
        self.assertNotIn("d", value["jwks"]["keys"][0])
        self.assertEqual(json.loads(cursor(value["business_cursor"]))["active"], "v1")
        bridge.public_jwks(json.dumps(value["jwks"]).encode())
        value["jwks"]["keys"][0]["d"] = "must-never-be-served"
        with self.assertRaises(ValueError):
            bridge.public_jwks(json.dumps(value["jwks"]).encode())

    def test_short_cursor_credentials_are_rejected(self):
        with self.assertRaises(ValueError):
            cursor(base64.b64encode(b"short").decode())

    def test_jwks_route_does_not_serve_arbitrary_files(self):
        body = json.dumps(new_keys()["jwks"]).encode()
        real_server = bridge.HTTPServer
        fake_path = Mock()
        fake_path.read_bytes.return_value = body
        with patch.object(bridge, "Path", return_value=fake_path), patch.object(
            bridge, "HTTPServer", side_effect=lambda _, handler: real_server(("127.0.0.1", 0), handler)
        ):
            server = bridge.jwks_server({"bind": "0.0.0.0", "port": 18091, "file": "/history-jwks/jwks.json"})
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                url = "http://127.0.0.1:" + str(server.server_port)
                with urllib.request.urlopen(url + "/.well-known/jwks.json") as response:
                    self.assertEqual(json.load(response), json.loads(body))
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(url + "/history/signing-key.pem")
                self.assertEqual(error.exception.code, 404)
            finally:
                server.shutdown(); server.server_close(); thread.join()
