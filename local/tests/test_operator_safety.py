"""Future CI tests: private state and source provenance, with no cluster calls."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from localdev import common, credentials


class LocalOperatorSafety(unittest.TestCase):
    def test_initialization_preserves_existing_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            local = Path(folder) / ".local"
            with patch.object(credentials, "LOCAL", local):
                credentials.initialize()
                before = (local / "credentials.json").read_bytes()
                credentials.initialize()
                self.assertEqual((local / "credentials.json").read_bytes(), before)
                self.assertEqual((local / "credentials.json").stat().st_mode & 0o777, 0o600)
                self.assertEqual(local.stat().st_mode & 0o777, 0o700)

    def test_remote_endpoint_is_rejected_before_any_kubectl_call(self):
        with tempfile.TemporaryDirectory() as folder:
            local = Path(folder)
            (local / "cluster-owner.json").write_text("{}")
            (local / "kubeconfig").write_text(json.dumps({
                "contexts": [{"name": common.CONTEXT, "context": {"cluster": "bad"}}],
                "clusters": [{"name": "bad", "cluster": {"server": "https://production.invalid"}}],
            }))
            with patch.object(common, "LOCAL", local), patch.object(common, "run") as process:
                with self.assertRaises(ValueError):
                    common.kube("get", "pods")
                process.assert_not_called()

    def test_dirty_source_has_a_distinct_snapshot_without_fabricating_a_commit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for command in (["init", "-q"], ["config", "user.email", "fixture@maintai.invalid"], ["config", "user.name", "Local fixture"]):
                subprocess.run(["git", "-C", str(root), *command], check=True)
            (root / "source.py").write_text("version = 1\n")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
            first = common.source_identity(root)
            (root / "source.py").write_text("version = 2\n")
            second = common.source_identity(root)
            self.assertEqual(first[0], second[0])
            self.assertFalse(first[1])
            self.assertTrue(second[1])
            self.assertNotEqual(first[2], second[2])

    def test_remote_url_cannot_contain_credentials_or_a_local_path(self):
        for value in ("file:///tmp/repository.git", "https://user:secret@example.invalid/repo.git", "ssh://example.invalid/repo.git"):
            with self.assertRaises(ValueError):
                common.repository_url(value)

    def test_mutable_and_unconfigured_build_bases_are_refused(self):
        for source in ("FROM python:latest\n", "ARG BASE\nFROM ${BASE}\n", "# no runtime yet\n"):
            with self.assertRaises(ValueError):
                common.require_pinned_bases(source)
        common.require_pinned_bases("ARG BASE\nFROM ${BASE} AS build\nFROM build\n", ["--build-arg", "BASE=python@sha256:" + "a" * 64])


if __name__ == "__main__":
    unittest.main()
