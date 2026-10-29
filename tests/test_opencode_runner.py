"""No credentials or model requests: verify OpenCode protocol and persistence."""

import unittest
import threading
import json

import test_local_runner as fixtures
from laomedo.agents.agents.opencode.agent import OpenCodeAgent
from laomedo.agents.errors import RunnerError
from laomedo.agents.agents.base.acp.models import AcpTurn
from laomedo.agents.agents.base.utils import _hash_tree
from laomedo.agents.agents.base.utils import _json


class Backend:
    """Internal ACP boundary fixture, never a live acceptance result."""

    sessions = 0

    def __init__(self, workspace, evidence):
        self.workspace = workspace
        self.log = (evidence / "raw-events.jsonl").open("a")
        self.termination_verified = False

    def models(self):
        self.log.write("models\n")
        self.log.flush()
        return [{"id": "test/model", "efforts": ["default"]}]

    def run(self, task, *, model, session_id, cancelled, capture, on_session):
        if cancelled.is_set():
            raise RunnerError("opencode_cancelled_before_dispatch")
        if session_id is None:
            type(self).sessions += 1
            session_id = "ses_test" + str(self.sessions)
        on_session(session_id)
        capture.begin(session_id, task)
        self.log.write("session/prompt\n")
        self.log.flush()
        (self.workspace / "output.txt").write_text("internal fixture")
        updates = [
            {
                "sessionUpdate": "tool_call",
                "toolCallId": "tool1",
                "title": "skill",
                "status": "completed",
                "rawInput": {"name": "sample"},
            },
            {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": "fixture answer"},
            },
        ]
        for update in updates:
            capture.update(session_id, update)
        capture.finish(session_id, "completed")
        return AcpTurn(
            session_id=session_id,
            stop_reason="end_turn",
            answer="fixture answer",
            updates=updates,
        )

    def cancel(self):
        pass

    def check_auth_fresh(self):
        pass

    def history_reader(self):
        return None

    def close(self):
        self.log.close()
        self.termination_verified = True


class OpenCodeTests(unittest.TestCase):
    def test_inherited_handoff_validates_provenance_before_execution(self):
        from uuid import uuid4

        handoff = {
            "execution_id": str(uuid4()),
            "step": 0,
            "source": {"provider": "opencode", "run_id": str(uuid4())},
            "workspace_policy": "independent",
        }
        record = self.runner._prepare({**self.payload, "handoff": handoff})
        self.assertEqual(record["handoff"], handoff)
        handoff["step"] = -1
        self.assertEqual(record["handoff"]["step"], 0)
        with self.assertRaisesRegex(RunnerError, "invalid_handoff_provenance"):
            self.runner._prepare({**self.payload, "handoff": handoff})
        with self.assertRaisesRegex(RunnerError, "invalid_handoff_origin"):
            self.runner._prepare(
                {
                    **self.payload,
                    "handoff": {
                        **handoff,
                        "step": 0,
                        "source": {"provider": "foreign", "run_id": str(uuid4())},
                    },
                }
            )

    def test_run_waits_for_catalog_cleanup_without_overlapping_profiles(self):
        entered, released, attempted = (
            threading.Event(),
            threading.Event(),
            threading.Event(),
        )
        waiting = threading.Event()

        class ObservedLock:
            def __init__(self):
                self.lock = threading.Lock()

            def acquire(self, *args, **kwargs):
                if kwargs.get("timeout") == 30:
                    waiting.set()
                return self.lock.acquire(*args, **kwargs)

            def release(self):
                self.lock.release()

            def __enter__(self):
                self.acquire()
                return self

            def __exit__(self, *args):
                self.release()

        self.runner._opencode_catalog_lock = ObservedLock()

        class PausedCatalog(Backend):
            def models(self):
                if "catalog" in str(self.workspace):
                    entered.set()
                    if not released.wait(45):
                        raise TimeoutError()
                return super().models()

        self.runner.transport_factory = PausedCatalog
        catalog_result = {}
        run_result = {}
        errors = []

        def catalog():
            try:
                catalog_result.update(self.runner.model_catalog())
            except Exception as exc:
                errors.append(exc)

        def run():
            attempted.set()
            try:
                run_result.update(self.runner.start(self.payload))
            except Exception as exc:
                errors.append(exc)

        a = threading.Thread(target=catalog)
        b = threading.Thread(target=run)
        a.start()
        try:
            self.assertTrue(entered.wait(15))
            b.start()
            self.assertTrue(attempted.wait(15))
            self.assertTrue(waiting.wait(15))
            self.assertFalse(run_result)
        finally:
            released.set()
            a.join(20)
            if b.ident is not None:
                b.join(20)
        self.assertFalse(a.is_alive())
        self.assertFalse(b.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(run_result["status"], "completed")
        self.assertEqual(catalog_result["submitted_turns"], 0)

    def test_exhausted_resume_preserves_completed_record_and_snapshot(self):
        # This ceiling belongs to the isolated experiment harness only.
        from verification_runner import VerificationOpenCodeRunner

        self.runner = VerificationOpenCodeRunner(
            self.runner.state,
            self.runner.store.root,
            self.source,
            transport_factory=Backend,
            max_model_turns=1,
        )
        run = self.runner.start(self.payload)
        before = (self.runner._run_dir(run["run_id"]) / "record.json").read_bytes()
        with self.assertRaisesRegex(RunnerError, "model_turn_cap_reached"):
            self.runner.resume(
                run["run_id"],
                "Continue",
                expected_post_run_hash=run["post_run_hash"],
                expected_thread_id=run["thread_id"],
                model="test/model",
                effort="default",
            )
        self.assertEqual(
            (self.runner._run_dir(run["run_id"]) / "record.json").read_bytes(), before
        )
        self.assertFalse(self.runner.lock.locked())

    def test_catalog_refuses_shared_profile_access_while_runner_is_busy(self):
        self.runner.lock.acquire()
        try:
            with self.assertRaisesRegex(RunnerError, "runner_busy"):
                self.runner.model_catalog()
        finally:
            self.runner.lock.release()

    def test_catalog_only_reads_native_metadata_without_charging_turns(self):
        calls = []

        class CatalogBackend(Backend):
            def models(self):
                calls.append("models")
                return super().models()

        self.runner.transport_factory = CatalogBackend
        result = self.runner.model_catalog()
        self.assertEqual(
            result,
            {
                "models": [{"id": "test/model", "efforts": ["default"]}],
                "submitted_turns": 0,
            },
        )
        self.assertEqual(self.runner.model_catalog(), result)
        self.assertEqual(calls, ["models"])
        self.assertFalse((self.runner.state / "turn-ledger.json").exists())
        self.assertEqual(list((self.runner.state / "catalog").iterdir()), [])

    def test_empty_skill_set_is_valid_and_unselected_files_are_still_rejected(self):
        payload = {
            key: value for key, value in self.payload.items() if key != "skill_ref"
        }
        payload["skill_refs"] = []
        record = self.runner._prepare(payload)
        root = self.runner._run_dir(record["run_id"]) / "workspace"
        self.runner._verify_pinned_skills(root, record)
        (root / ".agents/skills/unselected").mkdir()
        with self.assertRaisesRegex(RunnerError, "pinned_skill_workspace_changed"):
            self.runner._verify_pinned_skills(root, record)

    def test_cancel_before_session_does_not_submit_or_charge(self):
        entered, released = threading.Event(), threading.Event()

        class PausingBackend(Backend):
            def models(self):
                entered.set()
                if not released.wait(45):
                    raise TimeoutError()
                return super().models()

        self.runner.transport_factory = PausingBackend
        result = {}
        thread = threading.Thread(
            target=lambda: result.update(self.runner.start(self.payload))
        )
        thread.start()
        try:
            self.assertTrue(entered.wait(15))
            run_id = next(iter(self.runner.cancel_flags))
            response = self.runner.cancel(run_id)
            self.assertTrue(response["cancel_requested"])
            self.assertFalse(response["cancel_acknowledged"])
        finally:
            released.set()
            thread.join(20)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result["status"], "cancelled")
        self.assertIsNone(result.get("attempt_number"))
        self.assertFalse((self.runner.state / "turn-ledger.json").exists())
        self.assertNotIn(
            "session/prompt",
            (self.runner._run_dir(run_id) / "raw-events.jsonl").read_text(),
        )

    def test_cancel_after_reservation_skips_message_post(self):
        reserved, released = threading.Event(), threading.Event()
        original = self.runner._reserve_turn

        def pause_reservation():
            attempt = original()
            reserved.set()
            if not released.wait(45):
                raise TimeoutError()
            return attempt

        self.runner._reserve_turn = pause_reservation
        result = {}
        thread = threading.Thread(
            target=lambda: result.update(self.runner.start(self.payload))
        )
        thread.start()
        try:
            self.assertTrue(reserved.wait(15))
            run_id = next(iter(self.runner.cancel_flags))
            self.assertTrue(self.runner.cancel(run_id)["cancel_requested"])
        finally:
            released.set()
            thread.join(20)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["attempt_number"], 1)
        self.assertNotIn(
            "session/prompt",
            (self.runner._run_dir(run_id) / "raw-events.jsonl").read_text(),
        )

    def test_auth_expiry_rejected_before_turn_reservation(self):
        class ExpiredBackend(Backend):
            def check_auth_fresh(self):
                raise RunnerError("opencode_console_token_refresh_required")

        self.runner.transport_factory = ExpiredBackend
        run = self.runner.start(self.payload)
        self.assertEqual(run["status"], "failed")
        self.assertEqual(
            run["error_category"], "opencode_console_token_refresh_required"
        )
        self.assertFalse((self.runner.state / "turn-ledger.json").exists())

    def test_agent_skill_edit_invalidates_completed_run(self):
        class MutatingBackend(Backend):
            def run(self, *args, **kwargs):
                (self.workspace / ".agents/skills/sample/SKILL.md").write_text(
                    "changed by worker"
                )
                return super().run(*args, **kwargs)

        self.runner.transport_factory = MutatingBackend
        run = self.runner.start(self.payload)
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["error_category"], "pinned_skill_workspace_changed")
        self.assertIsNone(run["post_run_hash"])

    def test_resume_rejects_legacy_snapshot_with_modified_or_added_skill(self):
        for change in ("modify", "add"):
            with self.subTest(change=change):
                run = self.runner.start(self.payload)
                root = self.runner._run_dir(run["run_id"])
                for name in ("workspace", "post-run"):
                    skills = root / name / ".agents/skills"
                    if change == "modify":
                        (skills / "sample/SKILL.md").write_text(
                            "changed after first turn"
                        )
                    else:
                        extra = skills / "new-skill"
                        extra.mkdir()
                        (extra / "SKILL.md").write_text("new skill")
                altered = _hash_tree(root / "workspace")
                self.assertEqual(altered, _hash_tree(root / "post-run"))
                run["post_run_hash"] = altered
                _json(root / "record.json", run)
                with self.assertRaisesRegex(
                    RunnerError, "pinned_skill_workspace_changed"
                ):
                    self.runner.resume(
                        run["run_id"],
                        "Continue",
                        expected_post_run_hash=altered,
                        expected_thread_id=run["thread_id"],
                        model="test/model",
                        effort="default",
                    )

    def test_corrupt_record_does_not_leave_runner_locked(self):
        run = self.runner.start(self.payload)
        (self.runner._run_dir(run["run_id"]) / "record.json").write_text("{broken")
        with self.assertRaises(json.JSONDecodeError):
            self.runner._execute(run["run_id"], "Continue", resume=True)
        self.assertFalse(self.runner.lock.locked())

    def test_duplicate_acp_tool_deltas_are_counted_once(self):
        outcome = AcpTurn(
            session_id="s",
            stop_reason="end_turn",
            answer="done",
            updates=[
                {
                    "sessionUpdate": "tool_call",
                    "toolCallId": "call-1",
                    "title": "exec",
                    "status": "pending",
                },
                {
                    "sessionUpdate": "tool_call_update",
                    "toolCallId": "call-1",
                    "status": "completed",
                },
            ],
        )
        self.assertEqual(len(outcome.tool_calls()), 1)
        self.assertEqual(outcome.tool_calls()[0]["status"], "completed")

    def test_null_skill_input_does_not_raise_attribute_error(self):
        class NullSkill(Backend):
            def run(self, *args, **kwargs):
                result = super().run(*args, **kwargs)
                result.updates[0]["rawInput"] = None
                return result

        self.runner.transport_factory = NullSkill
        run = self.runner.start(self.payload)
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["skills"][0]["use_evidence"], "offered")

    def test_native_abort_unblocking_incomplete_response_preserves_cancelled_status(
        self,
    ):
        entered, released = threading.Event(), threading.Event()

        class AbortedBackend(Backend):
            def run(self, task, *, model, session_id, cancelled, capture, on_session):
                entered.set()
                if not released.wait(30):
                    raise TimeoutError()
                return AcpTurn(
                    session_id="ses_cancelled",
                    stop_reason="cancelled",
                    answer="",
                    updates=[],
                )

            def cancel(self):
                released.set()

        self.runner.transport_factory = AbortedBackend
        result = {}
        thread = threading.Thread(
            target=lambda: result.update(self.runner.start(self.payload))
        )
        thread.start()
        try:
            self.assertTrue(entered.wait(15))
            run_id = next(iter(self.runner.cancel_flags))
            ack = self.runner.cancel(run_id)
            self.assertFalse(ack["cancel_acknowledged"])
        finally:
            released.set()
            thread.join(20)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(self.runner.status(result["run_id"])["status"], "cancelled")
        self.assertIsNone(result["error_category"])

    def setUp(self):
        # Reuse only the fixture setup, not the Codex provider test cases.
        fixtures.LocalRunnerTests.setUp(self)
        self.runner = OpenCodeAgent(
            self.root.parent / (self.root.name + "-runner"),
            self.root.parent / (self.root.name + "-skill-store"),
            self.source,
            transport_factory=Backend,
        )
        self.addCleanup(
            lambda: __import__("shutil").rmtree(self.runner.state, ignore_errors=True)
        )
        self.payload = {
            "task": "Read skill",
            "model": "test/model",
            "effort": "default",
            "skill_ref": {
                "skill_id": "sample",
                "revision_id": self.revision["revision_id"],
                "tree_hash": self.revision["tree_hash"],
            },
        }

    def test_old_verification_ceiling_cannot_block_normal_run(self):
        ledger = self.runner.state / "turn-ledger.json"
        ledger.write_text(
            json.dumps({"attempted_turns": 500, "max_authorized_turns": 1})
        )
        run = self.runner.start(self.payload)
        self.assertEqual(run["status"], "completed")
        self.assertEqual(
            json.loads(ledger.read_text()),
            {"attempted_turns": 500, "max_authorized_turns": 1},
        )

    def test_async_start_uses_opencode_identity_and_cancel_before_dispatch_costs_no_turn(
        self,
    ):
        from uuid import uuid4

        gate = threading.Event()
        record = self.runner.start_async(
            {**self.payload, "request_id": str(uuid4())}, response_gate=gate
        )
        self.assertEqual(record["provider"], "opencode")
        cancelled = self.runner.cancel(record["run_id"])
        self.assertTrue(cancelled["cancel_confirmed"])
        gate.set()
        self.assertEqual(self.runner.status(record["run_id"])["status"], "cancelled")
        self.assertFalse((self.runner.state / "turn-ledger.json").exists())

    def test_resume_activity_contains_only_new_native_messages(self):
        from uuid import uuid4

        first = self.runner.start(self.payload)
        root = self.runner._run_dir(first["run_id"])
        initial = json.loads(
            (
                root
                / "activity-attempts"
                / (first["activity_initial_attempt_id"] + ".json")
            ).read_text()
        )
        selected = str(uuid4())
        second = self.runner.resume(
            first["run_id"],
            "New turn",
            expected_post_run_hash=first["post_run_hash"],
            expected_thread_id=first["thread_id"],
            model="test/model",
            effort="default",
            activity_attempt_id=selected,
        )
        self.assertTrue(second["attempt_finished"])
        self.assertTrue(second["snapshot_ready"])
        attempt = json.loads(
            (root / "activity-attempts" / (selected + ".json")).read_text()
        )
        self.assertEqual(attempt["native_start"], initial["native_end"])
        from laomedo.agents.activity.runner.feed import read_feed

        events = read_feed(
            root / "activity-events.jsonl",
            after=attempt["native_start"],
            before=attempt["native_end"],
        )["events"]
        texts = [
            event["event"]["params"]["item"]["text"]
            for event in events
            if event["event"]["method"] == "item/completed"
            and "text" in event["event"]["params"]["item"]
        ]
        self.assertIn("New turn", texts)
        self.assertNotIn("Read skill", texts)
        with self.assertRaisesRegex(RunnerError, "activity_attempt_already_exists"):
            self.runner.resume(
                first["run_id"],
                "Replay",
                expected_post_run_hash=second["post_run_hash"],
                expected_thread_id=first["thread_id"],
                model="test/model",
                effort="default",
                activity_attempt_id=selected,
            )

    def test_otel_attempt_boundaries_isolate_resume_feed(self):
        from unittest.mock import patch
        from uuid import uuid4
        from laomedo.agents.activity.runner.feed import read_feed
        from laomedo.agents.activity.runner.feed import receipt

        def export(root, start, session, model):
            with (root / "otel-events.jsonl").open("a") as stream:
                stream.write(
                    json.dumps(
                        receipt(
                            {
                                "method": "otel/record",
                                "params": {
                                    "attributes": {"conversation.id": session},
                                    "marker": start,
                                },
                            }
                        )
                    )
                    + "\n"
                )
            return True

        with patch(
            "laomedo.agents.agents.opencode.activity.telemetry.export_attempt", side_effect=export
        ):
            first = self.runner.start(self.payload)
            root = self.runner._run_dir(first["run_id"])
            initial = json.loads(
                (
                    root
                    / "activity-attempts"
                    / (first["activity_initial_attempt_id"] + ".json")
                ).read_text()
            )
            selected = str(uuid4())
            self.runner.resume(
                first["run_id"],
                "Second turn",
                expected_post_run_hash=first["post_run_hash"],
                expected_thread_id=first["thread_id"],
                model="test/model",
                effort="default",
                activity_attempt_id=selected,
            )
            second = json.loads(
                (root / "activity-attempts" / (selected + ".json")).read_text()
            )
        self.assertEqual((initial["otel_start"], initial["otel_end"]), (0, 1))
        self.assertEqual((second["otel_start"], second["otel_end"]), (1, 2))
        events = read_feed(
            root / "otel-events.jsonl",
            after=second["otel_start"],
            before=second["otel_end"],
        )["events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"]["params"]["marker"], second["native_start"])

    def test_capture_failure_cannot_claim_complete_execution_evidence(self):
        from unittest.mock import patch

        with patch(
            "laomedo.agents.activity.acp.capture.AcpCapture.update",
            side_effect=RunnerError("runner_transport_failed"),
        ):
            result = self.runner.start(self.payload)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["snapshot_ready"])
        self.assertEqual(result["error_category"], "runner_transport_failed")

    def test_async_variant_rejected_before_workspace_preparation(self):
        from uuid import uuid4

        with self.assertRaisesRegex(RunnerError, "unsupported_opencode_effort"):
            self.runner.start_async(
                {**self.payload, "effort": "high", "request_id": str(uuid4())}
            )
        self.assertEqual(list((self.runner.state / "runs").iterdir()), [])

    def test_fresh_restart_resume_and_evidence(self):
        run = self.runner.start(self.payload)
        self.assertEqual(run["status"], "completed")
        # ACP titles are display text, not evidence that a native skill ran.
        self.assertEqual(run["skills"][0]["use_evidence"], "offered")
        self.assertIsNone(run["usage"])
        restarted = OpenCodeAgent(
            self.runner.state,
            self.runner.store.root,
            self.source,
            transport_factory=Backend,
        )
        resumed = restarted.resume(
            run["run_id"],
            "Continue",
            expected_post_run_hash=run["post_run_hash"],
            expected_thread_id=run["thread_id"],
            model="test/model",
            effort="default",
        )
        self.assertEqual(resumed["thread_id"], run["thread_id"])
        self.assertEqual(len(resumed["turns"]), 2)
        fresh = restarted.start(self.payload)
        self.assertNotEqual(fresh["run_id"], run["run_id"])
        self.assertNotEqual(fresh["thread_id"], run["thread_id"])

    def test_unsupported_effort_before_dispatch(self):
        with self.assertRaisesRegex(RunnerError, "unsupported_opencode_effort"):
            self.runner.start({**self.payload, "effort": "high"})

    def test_production_transport_is_not_silently_enabled(self):
        self.runner.transport_factory = None
        with self.assertRaisesRegex(
            RunnerError, "opencode_isolated_transport_required"
        ):
            self.runner.start(self.payload)
        self.assertEqual(self.runner.preflight()["status"], "blocked")

    def test_running_tool_is_not_completed(self):
        class Outstanding(Backend):
            def run(self, *args, **kwargs):
                result = super().run(*args, **kwargs)
                result.updates[0]["status"] = "running"
                return result

        self.runner.transport_factory = Outstanding
        result = self.runner.start(self.payload)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_category"], "opencode_outstanding_tool")

    def test_non_success_terminal_reason_is_not_completed(self):
        class Truncated(Backend):
            def run(self, *args, **kwargs):
                result = super().run(*args, **kwargs)
                result.stop_reason = "max_tokens"
                return result

        self.runner.transport_factory = Truncated
        result = self.runner.start(self.payload)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_category"], "opencode_response_not_terminal")

    def test_multiple_skills_remain_pinned(self):
        second_source = self.root / "second-source"
        second_source.mkdir()
        (second_source / "SKILL.md").write_text("---\nname: second\n---\nUse amber.\n")
        second = self.runner.store.import_skill("second", second_source)
        refs = [
            self.payload["skill_ref"],
            {
                "skill_id": "second",
                "revision_id": second["revision_id"],
                "tree_hash": second["tree_hash"],
            },
        ]
        payload = {
            key: value for key, value in self.payload.items() if key != "skill_ref"
        }
        run = self.runner.start({**payload, "skill_refs": refs})
        self.assertEqual(run["status"], "completed")
        self.assertEqual(
            [item["skill_id"] for item in run["skills"]], ["sample", "second"]
        )
        self.assertEqual(run["skills"][1]["use_evidence"], "offered")

    def test_resume_rejects_workspace_mutation(self):
        run = self.runner.start(self.payload)
        args = {
            "expected_post_run_hash": run["post_run_hash"],
            "expected_thread_id": run["thread_id"],
            "model": "test/model",
            "effort": "default",
        }
        (self.runner._run_dir(run["run_id"]) / "workspace/output.txt").write_text(
            "changed"
        )
        with self.assertRaisesRegex(RunnerError, "workspace_changed_since_snapshot"):
            self.runner.resume(run["run_id"], "Continue", **args)


if __name__ == "__main__":
    unittest.main()
