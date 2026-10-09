"""Credential-free wiring checks for the opt-in join service."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from laomedo.langflow_join_service import build_service
from laomedo.workflow_run_store import LaunchError


class LangflowJoinServiceTests(unittest.TestCase):
    def test_private_files_wire_service_without_exposing_tokens(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            bridge = root / "bridge.token"
            runner = root / "runner.token"
            bridge.write_text("synthetic-bridge", encoding="utf-8")
            runner.write_text("synthetic-runner", encoding="utf-8")
            with patch("laomedo.langflow_join_service.LangflowLocalClient") as client:
                server = build_service(
                    store_path=root / "runs.sqlite3",
                    bridge_token_file=bridge, runner_token_file=runner,
                    langflow_url="http://127.0.0.1:7860",
                    runner_url="http://127.0.0.1:8765", port=0)
                try:
                    client.assert_called_once_with("http://127.0.0.1:7860")
                    self.assertTrue((root / "runs.sqlite3").is_file())
                    self.assertNotEqual(server.server_port, 0)
                finally:
                    server.server_close()
            with self.assertRaisesRegex(LaunchError, "join_private_paths_must_differ"):
                build_service(
                    store_path=bridge, bridge_token_file=bridge,
                    runner_token_file=runner,
                    langflow_url="http://127.0.0.1:7860",
                    runner_url="http://127.0.0.1:8765", port=0)


if __name__ == "__main__":
    unittest.main()
