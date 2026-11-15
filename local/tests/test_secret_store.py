import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from localdev import secret_store
from localdev.secret_store import documents, gitops_document, put_local_secrets


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
        with self.assertRaises(ValueError):
            gitops_document("chiendz11", "")

    def test_main_restores_gitops_entry_only_from_private_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            secrets_dir = root / "secrets"
            secrets_dir.mkdir(mode=0o700)
            (root / "credentials.json").write_text(
                json.dumps({
                    "postgres": {
                        "business_api_password": "a",
                        "processing_worker_password": "b",
                        "processing_reader_password": "c",
                        "knowledge_owner_password": "d",
                        "drift_owner_password": "e",
                    },
                    "minio": {"storage_password": "s"},
                }),
                encoding="utf-8",
            )
            groq = secrets_dir / "groq-api-key"
            groq.write_text("groq-fixture\n", encoding="utf-8")
            os.chmod(groq, 0o600)
            pat = secrets_dir / "image-updater-pat"
            pat.write_text("pat-fixture\n", encoding="utf-8")
            os.chmod(pat, 0o644)
            user = secrets_dir / "image-updater-username"
            user.write_text("chiendz11\n", encoding="utf-8")
            os.chmod(user, 0o600)

            with patch.object(secret_store, "LOCAL", root), patch.object(secret_store, "put_local_secrets"):
                with self.assertRaisesRegex(ValueError, "mode600"):
                    secret_store.main()

            os.chmod(pat, 0o600)
            with patch.object(secret_store, "LOCAL", root), patch.object(secret_store, "put_local_secrets") as put:
                secret_store.main()
                payload = put.call_args.args[0]
                self.assertEqual(payload["maintai/local/gitops"], {"username": "chiendz11", "password": "pat-fixture"})
