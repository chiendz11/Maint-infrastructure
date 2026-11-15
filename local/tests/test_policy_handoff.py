"""The local operator forwards app policy/source checks and injects Image Updater PAT safely."""

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from localdev import cli


class PolicyHandoff(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "receipts").mkdir()
        identity = self.root / "data/fixtures/model-identity.json"
        identity.parent.mkdir(parents=True)
        identity.write_text("{}")
        self.profile = {
            "machine_count": 5,
            "components": {
                "processing-worker": {
                    "enabled": True,
                    "files": {
                        "model_identity": {
                            "path": "/local/fixtures/model-identity.json",
                            "sha256": hashlib.sha256(identity.read_bytes()).hexdigest(),
                        }
                    },
                }
            },
        }
        self.profile_path = self.root / "profile.json"
        self.app = self.root / "app"

    def prepare(self):
        self.profile_path.write_text(json.dumps(self.profile))
        with (
            patch.object(cli, "LOCAL", self.root),
            patch.object(cli, "settings", return_value={"machine_count": 5}),
            patch.object(cli, "checkout", return_value=self.app),
            patch.object(cli, "verify_application_source") as verify,
        ):
            cli.prepare(SimpleNamespace(target="apps", profile=str(self.profile_path)))
            return verify

    def test_app_source_is_verified_and_no_private_policy_file_is_required(self):
        verify = self.prepare()
        verify.assert_called_once()
        self.assertEqual(verify.call_args.args[0], self.app)
        self.assertTrue((self.root / "release-receipts.json").exists())
        self.assertFalse((self.root / "data/fixtures/risk-policy.json").exists())

    def test_legacy_policy_file_is_rejected(self):
        self.profile["components"]["processing-worker"]["files"]["risk_policy"] = {
            "path": "/local/fixtures/risk-policy.json",
            "sha256": "a" * 64,
        }
        self.profile_path.write_text(json.dumps(self.profile))
        with (
            patch.object(cli, "LOCAL", self.root),
            patch.object(cli, "settings", return_value={"machine_count": 5}),
            patch.object(cli, "checkout", return_value=self.app),
            patch.object(cli, "verify_application_source"),
        ):
            with self.assertRaisesRegex(ValueError, "app-owned ConfigMap"):
                cli.prepare(SimpleNamespace(target="apps", profile=str(self.profile_path)))

    def test_image_updater_pat_requires_private_file_and_seeds_localstack(self):
        token_file = self.root / "pat.txt"
        token_file.write_text("github_pat_example_secret_12345\n", encoding="utf-8")
        os.chmod(token_file, 0o644)
        with patch.object(cli, "validate_context"), patch.object(cli, "LOCAL", self.root):
            with self.assertRaisesRegex(ValueError, "chmod 600"):
                cli.install_image_updater_pat(
                    SimpleNamespace(username="chiendz11", token_file=str(token_file), stdin=False)
                )

        os.chmod(token_file, 0o600)
        with patch.object(cli, "validate_context"), patch.object(cli, "LOCAL", self.root), patch.object(cli, "put_local_secrets") as mock_put:
            cli.install_image_updater_pat(
                SimpleNamespace(username="chiendz11", token_file=str(token_file), stdin=False)
            )
            mock_put.assert_called_once_with(
                {
                    "maintai/local/gitops": {
                        "username": "chiendz11",
                        "password": "github_pat_example_secret_12345",
                    }
                }
            )
            saved_pat = self.root / "secrets/image-updater-pat"
            saved_user = self.root / "secrets/image-updater-username"
            self.assertEqual(saved_pat.read_text(encoding="utf-8").strip(), "github_pat_example_secret_12345")
            self.assertEqual(saved_user.read_text(encoding="utf-8").strip(), "chiendz11")
            self.assertEqual(saved_pat.stat().st_mode & 0o077, 0)
            self.assertEqual(saved_user.stat().st_mode & 0o077, 0)


if __name__ == "__main__":
    unittest.main()
