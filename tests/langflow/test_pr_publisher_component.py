"""Pinned Langflow publisher node with no credential or network access."""

import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from lfx.schema import Data

PATH = Path(__file__).resolve().parents[2] / "components/laomedo/pr_publisher.py"
SPEC = importlib.util.spec_from_file_location("publisher_component", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
RUN = "11111111-1111-4111-8111-111111111111"


class PublisherComponentTests(unittest.TestCase):
    def node(self):
        node = MODULE.LaomedoPRPublisher()
        node.validation = Data(data={"contract_status": "accepted", "agent_submission": {
            "task_outcome": "success", "executor_status": "completed", "evidence_complete": True,
            "run_reference": {"run_id": RUN}}})
        node.runner_url = "http://127.0.0.1:8765"
        node.timeout_seconds = 30
        return node

    def test_success_only_posts_empty_body_and_exposes_no_capability(self):
        node = self.node()
        seen = []
        def open_request(req, timeout):
            seen.append(req)
            self.assertEqual(req.data, b"{}")
            self.assertEqual(req.full_url, "http://127.0.0.1:8765/v1/runs/" + RUN + "/publish")
            return io.BytesIO(json.dumps({"run_id": RUN, "publication_handoff": {
                "phase": "completed", "publication": {"state": "confirmed", "secret": "must-not-escape"}}}).encode())
        with patch.object(MODULE.Path, "read_text", return_value="dummy-runner-token"), \
                patch.object(MODULE.request.OpenerDirector, "open", side_effect=open_request):
            result = node.publication_output().data
        self.assertEqual(len(seen), 1)
        self.assertEqual(result, {"run_id": RUN, "phase": "completed", "publication_state": "confirmed"})

    def test_failure_rejection_and_uncertain_execution_do_not_dispatch(self):
        changes = [("contract_status", "rejected"), ("task_outcome", "failure"),
                   ("executor_status", "interrupted"), ("evidence_complete", "unknown")]
        for key, value in changes:
            node = self.node()
            target = node.validation.data if key == "contract_status" else node.validation.data["agent_submission"]
            target[key] = value
            with patch.object(MODULE.request.OpenerDirector, "open") as opened:
                self.assertEqual(node.publication_output().data["publication_state"], "not_dispatched")
                opened.assert_not_called()

    def test_lost_response_is_unknown_without_retry_or_error_text(self):
        with patch.object(MODULE.Path, "read_text", return_value="dummy-runner-token"), \
                patch.object(MODULE.request.OpenerDirector, "open", side_effect=TimeoutError("private secret")) as opened:
            result = self.node().publication_output().data
        self.assertEqual(opened.call_count, 1)
        self.assertEqual(result["publication_state"], "unknown")
        self.assertNotIn("secret", json.dumps(result))

    def test_unbound_or_remote_destination_refuses(self):
        for url in ("https://remote.example", "http://127.0.0.1:1/path", "http://user@localhost:1"):
            node = self.node(); node.runner_url = url
            with self.assertRaises(ValueError): node.publication_output()

    def test_foreign_response_does_not_claim_success(self):
        with patch.object(MODULE.Path, "read_text", return_value="dummy-runner-token"), \
                patch.object(MODULE.request.OpenerDirector, "open", return_value=io.BytesIO(
                    b'{"run_id":"foreign","publication_handoff":{"phase":"completed"}}')):
            self.assertEqual(self.node().publication_output().data["phase"], "unknown")
