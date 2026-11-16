"""Current continuation admission controls; simulated transport is not live acceptance."""

import unittest
from unittest.mock import patch, PropertyMock
from uuid import uuid4

from laomedo.agents.errors import RunnerError
from test_agents.test_runtime.models import RunnerCase
from test_agents.test_runtime.transport import FakeServer


class ContinuationTests(unittest.TestCase):
    def setUp(self):
        self.case = RunnerCase.create()
        self.addCleanup(self.case.close)

    def test_settled_cancel_and_failure_continue_same_session_without_success_artifact(
        self,
    ):
        for outcome in ("cancelled", "failed"):
            original_wait = FakeServer.wait_turn

            def terminal(server, *args):
                original_wait(server, *args)
                return outcome, "fixture_stop"

            with (
                self.subTest(outcome=outcome),
                patch.object(FakeServer, "cleanup_confirmed", True, create=True),
                patch.object(
                    FakeServer,
                    "streams_closed",
                    new_callable=PropertyMock,
                    return_value=True,
                ),
            ):
                with patch.object(FakeServer, "wait_turn", terminal):
                    result = self.case.runner.start(self.case.request())
                self.assertEqual(result["status"], outcome)
                self.assertFalse(result["snapshot_ready"])
                self.assertIsNone(result["post_run_hash"])
                self.assertIsNone(result["output_ref"])
                checkpoint = result["resume_checkpoint"]
                resumed = self.case.runner.resume(
                    result["run_id"],
                    "A distinct next message",
                    expected_thread_id=result["thread_id"],
                    expected_post_run_hash=checkpoint["workspace_hash"],
                    model="test-model",
                    effort="low",
                    activity_attempt_id=str(uuid4()),
                )
                self.assertEqual(
                    resumed["status"], "completed", resumed.get("error_category")
                )
                self.assertEqual(resumed["thread_id"], result["thread_id"])
                self.assertNotIn("resume_checkpoint", resumed)

    def test_unverified_cleanup_or_streams_cannot_create_a_checkpoint(self):
        with patch.object(
            FakeServer, "wait_turn", return_value=("cancelled", "fixture_stop")
        ):
            result = self.case.runner.start(self.case.request())
        self.assertNotIn("resume_checkpoint", result)
        with self.assertRaisesRegex(RunnerError, "resume_binding_mismatch"):
            self.case.runner.resume(
                result["run_id"],
                "continue",
                expected_thread_id=result["thread_id"],
                expected_post_run_hash="sha256:" + "0" * 64,
                model="test-model",
                effort="low",
            )

    def test_checkpoint_cannot_survive_runner_identity_change_or_workspace_edit(self):
        with (
            patch.object(FakeServer, "cleanup_confirmed", True, create=True),
            patch.object(
                FakeServer,
                "streams_closed",
                new_callable=PropertyMock,
                return_value=True,
            ),
            patch.object(
                FakeServer, "wait_turn", return_value=("cancelled", "fixture_stop")
            ),
        ):
            result = self.case.runner.start(self.case.request())
        binding = dict(
            expected_thread_id=result["thread_id"],
            expected_post_run_hash=result["resume_checkpoint"]["workspace_hash"],
            model="test-model",
            effort="low",
        )
        (
            self.case.runner._run_dir(result["run_id"]) / "workspace" / "edited.txt"
        ).write_text("changed")
        with self.assertRaisesRegex(RunnerError, "workspace_changed_since_snapshot"):
            self.case.runner.resume(result["run_id"], "continue", **binding)
        self.case.runner.instance_id = str(uuid4())
        with self.assertRaisesRegex(RunnerError, "resume_binding_mismatch"):
            self.case.runner.resume(result["run_id"], "continue", **binding)
