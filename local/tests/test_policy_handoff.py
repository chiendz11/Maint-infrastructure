"""The local operator forwards app source instead of staging risk policy data."""

import hashlib
import json
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
        self.gitops = self.root / "gitops"

    def prepare(self):
        self.profile_path.write_text(json.dumps(self.profile))
        with (
            patch.object(cli, "LOCAL", self.root),
            patch.object(cli, "settings", return_value={"machine_count": 5}),
            patch.object(
                cli,
                "checkout",
                side_effect=lambda key: self.app if key == "app_checkout" else self.gitops,
            ),
            patch.object(cli, "verify_application_source") as verify,
            patch.object(cli.subprocess, "run") as process,
        ):
            cli.prepare(SimpleNamespace(target="apps", profile=str(self.profile_path)))
            return verify, process

    def test_app_root_is_forwarded_and_no_private_policy_file_is_required(self):
        verify, process = self.prepare()
        verify.assert_called_once()
        self.assertEqual(verify.call_args.args[0], self.app)
        command = process.call_args.args[0]
        self.assertEqual(command[command.index("--app-root") + 1], str(self.app.resolve()))
        self.assertEqual(process.call_args.kwargs["cwd"], self.gitops)
        self.assertFalse((self.root / "data/fixtures/risk-policy.json").exists())

    def test_legacy_policy_file_is_rejected_before_calling_gitops(self):
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
            patch.object(cli.subprocess, "run") as process,
        ):
            with self.assertRaisesRegex(ValueError, "app-owned ConfigMap"):
                cli.prepare(SimpleNamespace(target="apps", profile=str(self.profile_path)))
            process.assert_not_called()


if __name__ == "__main__":
    unittest.main()
