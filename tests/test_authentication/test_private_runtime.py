"""Native directory and exclusive broker admission, without a model or GitHub call."""

from importlib.util import find_spec
from pathlib import Path
import sys
import tempfile
import unittest

if find_spec("starlette") is None:
    raise unittest.SkipTest("Optional ASGI runtime is not installed")

from laomedo.integrations.langflow.authentication.errors import PrivateSessionError
from laomedo.integrations.langflow.authentication.runtime import PrivateBrowserRuntime
from laomedo.integrations.langflow.authentication.settings import PrivateBrowserSettings


@unittest.skipUnless(sys.platform == "win32", "Native Windows broker admission")
class PrivateRuntimeAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def runtime(self, **values):
        return PrivateBrowserRuntime(
            PrivateBrowserSettings(
                **{
                    "origin": "http://127.0.0.1:17867",
                    "runtime_root": self.root / "private",
                    "public_roots": (self.root / "public",),
                    **values,
                }
            )
        )

    def test_marker_is_idempotent_and_bound_to_exact_origin(self):
        runtime = self.runtime()
        runtime._admit_directory()
        marker = runtime.root / "private-github.json"
        original = marker.read_bytes()
        runtime._admit_directory()
        self.assertEqual(marker.read_bytes(), original)
        with self.assertRaises(PrivateSessionError):
            self.runtime(origin="http://127.0.0.1:17868")._admit_directory()
        self.assertEqual(marker.read_bytes(), original)

    def test_public_source_or_agent_ancestor_is_refused_before_creation(self):
        for values in ({"public_roots": (self.root,)}, {"agent_mounts": (self.root,)}):
            with self.subTest(values=values):
                with self.assertRaises(PrivateSessionError):
                    self.runtime(**values)._admit_directory()
                self.assertFalse((self.root / "private").exists())

    def test_unowned_nonempty_directory_is_preserved(self):
        private = self.root / "private"
        private.mkdir()
        sentinel = private / "unrelated.txt"
        sentinel.write_text("preserve", encoding="utf-8")
        with self.assertRaises(PrivateSessionError):
            self.runtime()._admit_directory()
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve")
        self.assertFalse((private / "private-github.json").exists())

    def test_native_lock_excludes_second_broker_and_releases_for_restart(self):
        first, second = self.runtime(), self.runtime()
        first._admit_directory()
        self.addCleanup(first._release_process)
        self.addCleanup(second._release_process)
        first._claim_process()
        with self.assertRaises(PrivateSessionError):
            second._claim_process()
        first._release_process()
        second._claim_process()
        second._release_process()
