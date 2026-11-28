import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from localdev import cli, secret_store
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
                    "minio": {
                        "storage_password": "s",
                        "training_password": "t",
                        "inference_password": "i",
                        "drift_password": "dr",
                    },
                    "m7": {
                        "rag_token": "rt-fixture",
                        "drift_cursor_key": "k" * 64,
                    },
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
                self.assertEqual(payload["maintai/local/training"]["AWS_ACCESS_KEY_ID"], "maintai-training")
                self.assertEqual(payload["maintai/local/training"]["AWS_SECRET_ACCESS_KEY"], "t")
                self.assertEqual(payload["maintai/local/inference"]["AWS_ACCESS_KEY_ID"], "maintai-inference")
                self.assertEqual(payload["maintai/local/inference"]["AWS_SECRET_ACCESS_KEY"], "i")
                self.assertEqual(payload["maintai/local/drift"]["AWS_ACCESS_KEY_ID"], "maintai-drift")
                self.assertEqual(payload["maintai/local/drift"]["AWS_SECRET_ACCESS_KEY"], "dr")
                self.assertEqual(payload["maintai/local/m7"], {"rag-token": "rt-fixture", "drift-cursor-key": "k" * 64})

    def test_forward_argo_workflows_uses_isolated_loopback_forward(self):
        with patch.object(cli, "kube") as mock_kube:
            exit_code = cli.main(["forward", "argo-workflows"])
        self.assertEqual(exit_code, 0)
        mock_kube.assert_called_once_with(
            "port-forward",
            "--address=127.0.0.1",
            "service/argo-workflows-server",
            "12746:2746",
            namespace="argo",
        )


    def test_ssm_parameter_helpers_use_stdin_and_require_all_model_keys(self):
        champion = {
            "pipeline": "vid-p1",
            "metadata": "vid-m1",
            "evaluation": "vid-e1",
            "drift_reference": "vid-d1",
        }
        shadow = {
            "pipeline": "vid-p2",
            "metadata": "vid-m2",
            "evaluation": "vid-e2",
            "drift_reference": "vid-d2",
        }
        params = secret_store.build_model_version_parameters(champion, shadow)
        self.assertEqual(json.loads(params["/maintai/local/models/champion_versions"]), champion)
        self.assertEqual(json.loads(params["/maintai/local/models/shadow_versions"]), shadow)
        with self.assertRaisesRegex(ValueError, "Missing champion"):
            secret_store.build_model_version_parameters({"pipeline": "only"}, shadow)

        with patch("localdev.secret_store.kube") as execute:
            secret_store.put_local_ssm_parameters(params)
        args, kwargs = execute.call_args
        self.assertEqual(kwargs["namespace"], "localstack")
        self.assertIn("boto3.client('ssm',endpoint_url='http://localhost:4566'", args[-1])
        self.assertEqual(json.loads(kwargs["stdin"]), params)
