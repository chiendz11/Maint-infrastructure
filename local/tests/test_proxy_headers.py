"""The local TLS edge replaces forwarding metadata instead of trusting the caller."""

import importlib.util
import unittest
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "runtime/bridge.py"
spec = importlib.util.spec_from_file_location("local_demo_bridge", path)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class ProxyHeaders(unittest.TestCase):
    def test_transport_sets_scheme_and_preserves_auth(self):
        value = bridge.forwarded_headers({"Authorization": "Bearer fixture", "Host": "127.0.0.1:18490", "X-Forwarded-Proto": "http", "X-Forwarded-For": "attacker", "Forwarded": "proto=http", "Connection": "close"}, tls=True, client_host="10.42.0.1")
        self.assertEqual(value["X-Forwarded-Proto"], "https")
        self.assertEqual(value["X-Forwarded-For"], "10.42.0.1")
        self.assertEqual(value["Authorization"], "Bearer fixture")
        self.assertNotIn("Forwarded", value)
        self.assertNotIn("Connection", value)

    def test_plain_listener_cannot_claim_https(self):
        value = bridge.forwarded_headers({"X-Forwarded-Proto": "https"}, tls=False, client_host="127.0.0.1")
        self.assertEqual(value["X-Forwarded-Proto"], "http")
