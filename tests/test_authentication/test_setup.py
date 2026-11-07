"""Internal admission tests; these do not establish real browser/login acceptance."""

import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from uuid import uuid4


@unittest.skipUnless(sys.platform == "win32", "Native Windows launcher")
class NormalLoginSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="laomedo-login-admission-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.frontend = self.root / "frontend"
        self.frontend.mkdir()
        (self.frontend / "index.html").write_text("internal admission fixture")
        self.repo = Path(__file__).resolve().parents[2]
        self.launcher = self.repo / "tools/start_normal_login.ps1"
        self.powershell = shutil.which("powershell.exe")

    def prepare(self, runtime, port=17864, mode="Prepare"):
        return subprocess.run(
            [
                self.powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.launcher),
                "-Mode",
                mode,
                "-PythonExe",
                sys.executable,
                "-FrontendPath",
                str(self.frontend),
                "-RuntimeRoot",
                str(runtime),
                "-Port",
                str(port),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_preparation_is_idempotent_without_accounts_or_database(self):
        runtime = self.root / "runtime"
        first = self.prepare(runtime)
        self.assertEqual(first.returncode, 0, first.stderr)
        marker = (runtime / "normal-login.json").read_bytes()
        second = self.prepare(runtime)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(marker, (runtime / "normal-login.json").read_bytes())
        self.assertEqual(
            set(p.name for p in runtime.iterdir()),
            {"normal-login.json", "langflow", "registry"},
        )
        self.assertFalse(list((runtime / "langflow").iterdir()))
        self.assertEqual(json.loads(marker.decode("utf-8-sig"))["port"], 17864)

    def test_refuses_state_inside_checkout_without_creating_it(self):
        runtime = self.repo / ".test-state" / ("login-" + uuid4().hex)
        result = self.prepare(runtime)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outside Git checkouts", result.stderr)
        self.assertFalse(runtime.exists())

    def test_refuses_unowned_nonempty_directory_and_preserves_files(self):
        runtime = self.root / "another-app"
        runtime.mkdir()
        sentinel = runtime / "preserve.txt"
        sentinel.write_text("unrelated state")
        result = self.prepare(runtime)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sentinel.read_text(), "unrelated state")
        self.assertEqual(list(runtime.iterdir()), [sentinel])

    def test_refuses_origin_change_for_existing_runtime(self):
        runtime = self.root / "runtime"
        self.assertEqual(self.prepare(runtime).returncode, 0)
        marker = (runtime / "normal-login.json").read_bytes()
        result = self.prepare(runtime, port=17865)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fixed origin does not match", result.stderr)
        self.assertEqual(marker, (runtime / "normal-login.json").read_bytes())

    def test_refuses_relative_runtime(self):
        result = self.prepare("relative-runtime")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be absolute", result.stderr)

    def test_missing_frontend_does_not_create_runtime(self):
        (self.frontend / "index.html").unlink()
        runtime = self.root / "runtime"
        result = self.prepare(runtime)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing index.html", result.stderr)
        self.assertFalse(runtime.exists())

    def test_occupied_port_is_refused_before_runtime_import(self):
        runtime = self.root / "runtime"
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            result = self.prepare(runtime, listener.getsockname()[1], mode="Check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Port is already in use", result.stderr)
