"""Real native identity/lease startup, isolated from the test process's services."""

from importlib.util import find_spec
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(
    sys.platform == "win32" and find_spec("langflow") is not None,
    "Broker custody uses the optional native Windows runtime",
)
class PrivateBrokerStartupTests(unittest.TestCase):
    """Native login still works when the graph application is absent."""

    def test_native_identity_and_private_lease_without_graph_application(self):
        self.run_child()

    def test_curated_provider_identity_metadata_and_flow_persistence(self):
        self.run_child("providers")

    def run_child(self, mode=None):
        workspace = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="laomedo-broker-test-") as directory:
            root = Path(directory).resolve() / "runtime"
            root.mkdir()
            (root / "local-profiles.json").write_text(
                json.dumps(
                    {
                        "purpose": "laomedo-local-profiles",
                        "version": 1,
                        "port": 27889,
                    }
                ),
                encoding="utf-8",
            )
            (root / "langflow").mkdir()
            (root / "registry").mkdir()
            allowed = {
                "PATH",
                "SYSTEMROOT",
                "WINDIR",
                "TEMP",
                "TMP",
                "USERPROFILE",
                "APPDATA",
                "LOCALAPPDATA",
            }
            environment = {
                key: value
                for key, value in os.environ.items()
                if key.upper() in allowed
            }
            environment.update(
                {
                    "PYTHONPATH": os.pathsep.join(
                        (str(workspace.parent / "src"), str(workspace))
                    ),
                    "LAOMEDO_LOCAL_PROFILE_RUNTIME": str(root),
                    "LANGFLOW_CONFIG_DIR": str(root / "langflow"),
                    "LFX_CONFIG_DIR": str(root / "langflow"),
                    "LANGFLOW_DATABASE_URL": "sqlite:///"
                    + (root / "langflow" / "flow.db").as_posix(),
                    "LANGFLOW_AUTO_LOGIN": "false",
                    "LANGFLOW_SKIP_AUTH_AUTO_LOGIN": "false",
                    "LANGFLOW_ENABLE_SIGNUP": "false",
                    "LANGFLOW_NEW_USER_IS_ACTIVE": "true",
                    "LANGFLOW_EXTERNAL_AUTH_ENABLED": "false",
                    "LANGFLOW_API_KEY_SOURCE": "db",
                    "LANGFLOW_DO_NOT_TRACK": "true",
                    "LAOMEDO_ASSISTANT_STATE_ROOT": str(root / "assistant"),
                }
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "support.broker_startup",
                    *([mode] if mode else []),
                ],
                cwd=root,
                env=environment,
                capture_output=True,
                timeout=120,
            )
            # Captured native output can contain auth diagnostics; never include
            # it in assertion output or upload the child runtime as evidence.
            diagnostics = [
                line
                for line in result.stderr.decode("utf-8", errors="replace").splitlines()
                if line.startswith("BROKER_CHECK_FAILURE=")
            ]
            self.assertEqual(
                result.returncode,
                0,
                "native broker startup check failed " + " ".join(diagnostics),
            )
