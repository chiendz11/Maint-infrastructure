"""Application source locks reject revision drift and modified interface bytes."""

import copy
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path

from localdev.checks import verify_application_source


class ApplicationSourceLock(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for arguments in (["init", "-q"], ["config", "user.email", "fixture@maintai.invalid"], ["config", "user.name", "Source lock fixture"]):
            self.git(*arguments)
        (self.root / "interface.py").write_text("VERSION = 1\n")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        self.lock = {"schema_version": "1.0.0", "source_repository": "chiendz11/MaintAI",
                     "source_git_sha": self.git("rev-parse", "HEAD"),
                     "files": {"interface.py": hashlib.sha256((self.root / "interface.py").read_bytes()).hexdigest()}}

    def git(self, *arguments):
        return subprocess.check_output(["git", "-C", str(self.root), *arguments], text=True).strip()

    def test_exact_revision_and_selected_files_are_accepted(self):
        verify_application_source(self.root, self.lock)

    def test_modified_interface_at_the_same_revision_is_rejected(self):
        (self.root / "interface.py").write_text("VERSION = 2\n")
        with self.assertRaisesRegex(ValueError, "interface drift"):
            verify_application_source(self.root, self.lock)

    def test_new_revision_is_rejected_even_when_selected_files_match(self):
        (self.root / "another.py").write_text("VALUE = 1\n")
        self.git("add", ".")
        self.git("commit", "-qm", "later revision")
        with self.assertRaisesRegex(ValueError, "HEAD differs"):
            verify_application_source(self.root, self.lock)

    def test_wrong_repository_and_path_escape_are_rejected(self):
        lock = copy.deepcopy(self.lock)
        lock["source_repository"] = "someone/another-app"
        with self.assertRaisesRegex(ValueError, "lock identity"):
            verify_application_source(self.root, lock)
        lock = copy.deepcopy(self.lock)
        lock["files"] = {"../interface.py": "a" * 64}
        with self.assertRaisesRegex(ValueError, "Invalid application source lock entry"):
            verify_application_source(self.root, lock)


if __name__ == "__main__":
    unittest.main()
