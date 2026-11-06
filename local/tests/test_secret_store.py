import json
import unittest
from unittest.mock import patch

from localdev.secret_store import documents, put_local_secrets


class SecretStore(unittest.TestCase):
    def test_values_use_stdin_and_explicit_owned_endpoint(self):
        with patch("localdev.secret_store.kube") as execute:
            put_local_secrets({"maintai/local/llm": {"GROQ_API_KEY": "fixture-private-value"}})
        args, kwargs = execute.call_args
        self.assertNotIn("fixture-private-value", str(args))
        self.assertEqual(json.loads(kwargs["stdin"])["maintai/local/llm"]["GROQ_API_KEY"], "fixture-private-value")
        self.assertEqual(kwargs["namespace"], "localstack")
        self.assertIn("endpoint_url='http://localhost:4566'", args[-1])
        self.assertIn("region_name='ap-southeast-1'", args[-1])

    def test_missing_credentials_fail_instead_of_seeding_defaults(self):
        with self.assertRaises(KeyError):
            documents({"postgres": {}, "minio": {}}, "fixture-key")
        with self.assertRaises(ValueError):
            documents({}, "")
