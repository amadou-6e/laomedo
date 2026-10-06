"""The CLI summary must not imply semantic success from Docker process exit."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from laomedo.work_graph.local_launch import launch_local_saved_flow


class WorkGraphCliSummaryTests(unittest.TestCase):
    def test_process_exit_basis_and_incomplete_evidence_are_visible(self):
        with TemporaryDirectory() as directory:
            snapshot = Path(directory) / "snapshot.json"
            snapshot.write_text("{}", encoding="utf-8")
            grant_path = Path(directory) / "grants.sqlite"
            run_path = Path(directory) / "runs.sqlite"
            record = {"run_id": "run", "trace_id": "trace",
                "status": "completed", "completion_basis": "process_exit",
                "evidence_complete": 0, "dispatch_attempts": 1,
                "graph_revision": "sha256:fixture"}
            with (patch("laomedo.work_graph.local_launch.GraphSnapshot.from_dict",
                        return_value=object()),
                  patch("laomedo.work_graph.local_launch.LocalGrantAuthority",
                        return_value=Mock(path=grant_path)),
                  patch("laomedo.work_graph.local_launch._private_path",
                        return_value=run_path),
                  patch("laomedo.work_graph.local_launch.WorkflowRunStore"),
                  patch("laomedo.work_graph.local_launch.LangflowLocalClient"),
                  patch("laomedo.work_graph.local_launch.launch_github_docker_saved_flow_stage",
                        return_value=(record, "PRIVATE RESULT"))):
                summary = launch_local_saved_flow(snapshot_path=snapshot,
                    work_key="github:S-20", flow_id="fixture",
                    langflow_base="http://127.0.0.1:17874",
                    grant_store=grant_path, grant_ref="grant", run_store=run_path,
                    task="fixture")
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["completion_basis"], "process_exit")
        self.assertIs(summary["evidence_complete"], False)
        self.assertTrue(summary["output_present"])
        self.assertNotIn("PRIVATE RESULT", json.dumps(summary))


if __name__ == "__main__":
    unittest.main()
