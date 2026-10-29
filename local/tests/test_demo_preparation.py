"""Private credential files and honest image provenance; no real key or cluster."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from localdev import credentials, demo


class GroqSecret(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.local = Path(temporary.name)
        self.folder = self.local / "secrets"
        self.folder.mkdir()
        self.file = self.folder / "groq-api-key"

    def test_no_key_is_created_or_required_for_platform_bootstrap(self):
        with patch.object(credentials, "LOCAL", self.local):
            self.assertIsNone(credentials.groq_secret_resource(required=False))
            with self.assertRaises(ValueError):
                credentials.groq_secret_resource()
        self.assertFalse(self.file.exists())

    def test_private_file_becomes_only_the_scoped_secret(self):
        fixture = "gsk_" + "test_fixture_not_a_real_credential" * 2
        self.file.write_text(fixture + "\n")
        self.file.chmod(0o600)
        with (
            patch.object(credentials, "LOCAL", self.local),
            patch.object(credentials, "apply") as apply,
            patch("builtins.print") as output,
        ):
            credentials.install_groq_secret()
        document = apply.call_args.args[0][0]
        self.assertEqual(document["metadata"]["name"], "rag-groq")
        self.assertEqual(document["stringData"], {"GROQ_API_KEY": fixture})
        self.assertNotIn(fixture, str(output.call_args_list))

    def test_public_or_invalid_file_fails_without_exposing_value(self):
        for value, mode in (
            ("gsk_fixture", 0o644),
            ("invalid-value", 0o600),
            ("gsk_abc def", 0o600),
        ):
            self.file.write_text(value)
            self.file.chmod(mode)
            with (
                patch.object(credentials, "LOCAL", self.local),
                self.assertRaises(ValueError) as result,
            ):
                credentials.groq_secret_resource()
            self.assertNotIn(value, str(result.exception))


class ModelImageIdentity(unittest.TestCase):
    def test_config_id_is_not_silently_used_as_manifest_digest(self):
        with self.assertRaises(ValueError):
            demo.serving_reference(
                {"image_id": "sha256:" + "a" * 64},
                {"Id": "sha256:" + "a" * 64, "RepoDigests": []},
            )

    def test_actual_manifest_reference_is_preserved(self):
        reference = "maintai-local/ml-service@sha256:" + "b" * 64
        result = demo.serving_reference(
            {"image_id": "sha256:" + "a" * 64},
            {
                "Id": "sha256:" + "a" * 64,
                "RepoDigests": [reference],
                "Descriptor": {"digest": "sha256:" + "b" * 64},
            },
        )
        self.assertEqual(result, reference)

    def test_changed_image_or_descriptor_is_rejected(self):
        reference = "maintai-local/ml-service@sha256:" + "b" * 64
        for inspection in (
            {"Id": "sha256:" + "c" * 64},
            {
                "Id": "sha256:" + "a" * 64,
                "RepoDigests": [reference],
                "Descriptor": {"digest": "sha256:" + "c" * 64},
            },
        ):
            with self.assertRaises(ValueError):
                demo.serving_reference({"image_id": "sha256:" + "a" * 64}, inspection)
