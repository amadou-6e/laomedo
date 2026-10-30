"""Keep local and CI formatting consistent without rewriting sealed evidence."""

from pathlib import Path
from hashlib import sha256
from importlib.util import find_spec
import json
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(find_spec("black"), "Install the development extra for formatter checks")
class FormattingPolicyTests(unittest.TestCase):
    """Exercise Black's actual file discovery and failure status."""

    root = Path(__file__).resolve().parents[1]

    def test_new_python_file_is_checked_and_formatted(self):
        # Temporary maintained source remains discoverable without git add.
        with tempfile.TemporaryDirectory(prefix="black-policy-", dir=self.root) as name:
            source = Path(name, "new_module.py")
            source.write_text("value={ 'answer':42 }\n", encoding="utf-8")
            check = self._black("--check", name)
            self.assertEqual(check.returncode, 1, check.stderr)
            formatted = self._black(name)
            self.assertEqual(formatted.returncode, 0, formatted.stderr)
            self.assertEqual(source.read_text(encoding="utf-8"), 'value = {"answer": 42}\n')
            self.assertEqual(self._black("--check", name).returncode, 0)

    def test_explicit_sealed_file_is_not_reformatted(self):
        source = self.root.joinpath("experiments", "exp139", "run_flow.py")
        before = source.read_bytes()
        result = self._black("--check", "--verbose", str(source))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("force-exclude", result.stderr)
        self.assertEqual(source.read_bytes(), before)

    def test_ignored_private_state_is_not_discovered(self):
        with tempfile.TemporaryDirectory(prefix="black-policy-", dir=self.root) as name:
            folder = Path(name)
            folder.joinpath(".gitignore").write_text("private/\n", encoding="utf-8")
            private = folder.joinpath("private")
            private.mkdir()
            source = private.joinpath("credentials.py")
            source.write_text("not valid python!!!\n", encoding="utf-8")
            result = self._black("--check", name)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_sealed_source_bytes_keep_their_recorded_hashes(self):
        records = json.loads(
            self.root.joinpath("tools", "formatting", "historical-sources.json").read_text(
                encoding="utf-8"
            )
        )
        for record in records:
            with self.subTest(path=record["path"]):
                source = self.root.joinpath(record["path"])
                self.assertEqual(sha256(source.read_bytes()).hexdigest(), record["sha256"])
                for evidence in record["evidence"]:
                    self.assertIn(
                        record["sha256"],
                        self.root.joinpath(evidence).read_text(encoding="utf-8"),
                    )
                checked = self._black("--check", "--verbose", str(source))
                self.assertEqual(checked.returncode, 0, checked.stderr)
                self.assertIn("force-exclude", checked.stderr)

    def _black(self, *arguments):
        return subprocess.run(
            [sys.executable, "-m", "black", "--no-cache", *arguments],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
