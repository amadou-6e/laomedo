"""No credentials or model requests: verify OpenCode protocol and persistence."""

import unittest
import threading
import json

import test_local_runner as fixtures
from laomedo.opencode_runner import OpenCodeRunner, RunnerError, normalize_message, turn_parts
from laomedo.local_runner import _hash_tree, _json


class Backend:
    sessions = 0

    def __init__(self, workspace, evidence):
        self.workspace = workspace
        self.log = (evidence / "raw-events.jsonl").open("a")

    def call(self, method, path, payload=None):
        self.log.write(path + "\n")
        self.log.flush()
        if path == "/global/health":
            return {"healthy": True, "version": "1.18.33"}
        if path == "/provider":
            return {"connected": ["test"], "all": [{"id": "test", "models": {"model": {}}}]}
        if path == "/session":
            type(self).sessions += 1
            return {"id": "ses_test" + str(self.sessions)}
        if path.endswith("/message"):
            (self.workspace / "output.txt").write_text("observed fixture")
            return {"info": {"id": "msg_fixture", "role": "assistant", "time": {"completed": 1},
                             "sessionID": path.split("/")[2], "providerID": "test", "modelID": "model"},
                    "parts": [{"type": "text", "text": "fixture answer"},
                              {"type": "tool", "tool": "skill", "callID": "tool1",
                               "state": {"status": "completed", "input": {"name": "sample"},
                                         "output": "skill body"}}]}
        raise AssertionError(path)

    def close(self):
        self.log.close()


class OpenCodeTests(unittest.TestCase):
    def test_cancel_before_session_does_not_submit_or_charge(self):
        entered, released = threading.Event(), threading.Event()
        class PausingBackend(Backend):
            def call(self, method, path, payload=None):
                if path == '/provider':
                    entered.set()
                    self_waited = released.wait(3)
                    if not self_waited:
                        raise TimeoutError()
                return super().call(method, path, payload)
        self.runner.transport_factory = PausingBackend
        result = {}
        thread = threading.Thread(target=lambda: result.update(self.runner.start(self.payload)))
        thread.start()
        try:
            self.assertTrue(entered.wait(3))
            run_id = next(iter(self.runner.cancel_flags))
            response = self.runner.cancel(run_id)
            self.assertTrue(response['cancel_requested'])
            self.assertFalse(response['cancel_acknowledged'])
        finally:
            released.set()
            thread.join(4)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result['status'], 'cancelled')
        self.assertIsNone(result.get('attempt_number'))
        self.assertFalse((self.runner.state / 'turn-ledger.json').exists())
        self.assertNotIn('/message', (self.runner._run_dir(run_id) / 'raw-events.jsonl').read_text())

    def test_cancel_after_reservation_skips_message_post(self):
        reserved, released = threading.Event(), threading.Event()
        original = self.runner._reserve_turn
        def pause_reservation():
            attempt = original()
            reserved.set()
            if not released.wait(3):
                raise TimeoutError()
            return attempt
        self.runner._reserve_turn = pause_reservation
        result = {}
        thread = threading.Thread(target=lambda: result.update(self.runner.start(self.payload)))
        thread.start()
        try:
            self.assertTrue(reserved.wait(3))
            run_id = next(iter(self.runner.cancel_flags))
            self.assertTrue(self.runner.cancel(run_id)['cancel_requested'])
        finally:
            released.set()
            thread.join(4)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(result['attempt_number'], 1)
        self.assertNotIn('/message', (self.runner._run_dir(run_id) / 'raw-events.jsonl').read_text())

    def test_auth_expiry_rejected_before_turn_reservation(self):
        class ExpiredBackend(Backend):
            def check_auth_fresh(self):
                raise RunnerError('opencode_console_token_refresh_required')
        self.runner.transport_factory = ExpiredBackend
        run = self.runner.start(self.payload)
        self.assertEqual(run['status'], 'failed')
        self.assertEqual(run['error_category'], 'opencode_console_token_refresh_required')
        self.assertFalse((self.runner.state / 'turn-ledger.json').exists())

    def test_agent_skill_edit_invalidates_completed_run(self):
        class MutatingBackend(Backend):
            def call(self, method, path, payload=None):
                if path.endswith('/message') and method == 'POST':
                    (self.workspace / '.agents/skills/sample/SKILL.md').write_text('changed by worker')
                return super().call(method, path, payload)
        self.runner.transport_factory = MutatingBackend
        run = self.runner.start(self.payload)
        self.assertEqual(run['status'], 'failed')
        self.assertEqual(run['error_category'], 'pinned_skill_workspace_changed')
        self.assertIsNone(run['post_run_hash'])

    def test_resume_rejects_legacy_snapshot_with_modified_or_added_skill(self):
        for change in ('modify', 'add'):
            with self.subTest(change=change):
                run = self.runner.start(self.payload)
                root = self.runner._run_dir(run['run_id'])
                for name in ('workspace', 'post-run'):
                    skills = root / name / '.agents/skills'
                    if change == 'modify':
                        (skills / 'sample/SKILL.md').write_text('changed after first turn')
                    else:
                        extra = skills / 'new-skill'
                        extra.mkdir()
                        (extra / 'SKILL.md').write_text('new skill')
                altered = _hash_tree(root / 'workspace')
                self.assertEqual(altered, _hash_tree(root / 'post-run'))
                run['post_run_hash'] = altered
                _json(root / 'record.json', run)
                with self.assertRaisesRegex(RunnerError, 'pinned_skill_workspace_changed'):
                    self.runner.resume(run['run_id'], 'Continue',
                        expected_post_run_hash=altered, expected_thread_id=run['thread_id'],
                        model='test/model', effort='default')

    def test_corrupt_record_does_not_leave_runner_locked(self):
        run = self.runner.start(self.payload)
        (self.runner._run_dir(run['run_id']) / 'record.json').write_text('{broken')
        with self.assertRaises(json.JSONDecodeError):
            self.runner._execute(run['run_id'], 'Continue', resume=True)
        self.assertFalse(self.runner.lock.locked())

    def test_duplicate_native_tool_parts_are_counted_once(self):
        tool = {'type': 'tool', 'tool': 'laomedo_exec', 'callID': 'call-1',
                'state': {'status': 'completed', 'input': {}, 'output': 'ok'}}
        message = {'info': {'id': 'final', 'role': 'assistant', 'parentID': 'user-1',
                            'time': {'completed': 1}},
                   'parts': [tool, {'type': 'text', 'text': 'done'}]}
        steps = [{'info': {'id': 'previous', 'role': 'assistant', 'parentID': 'user-1'},
                  'parts': [tool]}, message]
        parts = turn_parts(message, steps)
        normalized = normalize_message({**message, 'parts': parts}, [])
        self.assertEqual(len(normalized['tools']), 1)

    def test_null_skill_input_does_not_raise_attribute_error(self):
        value = {'info': {'role': 'assistant', 'time': {'completed': 1}},
                 'parts': [{'type': 'text', 'text': 'done'}, {'type': 'tool', 'tool': 'skill',
                            'callID': 'call-1', 'state': {'status': 'completed', 'input': None}}]}
        self.assertEqual(len(normalize_message(value, [{'skill_id': 'sample'}])['tools']), 1)

    def test_native_abort_unblocking_incomplete_response_preserves_cancelled_status(self):
        entered, released = threading.Event(), threading.Event()
        class AbortedBackend(Backend):
            def call(self, method, path, payload=None):
                if path.endswith('/abort'):
                    released.set()
                    return True
                if path.endswith('/message') and method == 'POST':
                    entered.set()
                    if not released.wait(3):
                        raise TimeoutError()
                    return {'info': {}, 'parts': []}
                return super().call(method, path, payload)
        self.runner.transport_factory = AbortedBackend
        result = {}
        thread = threading.Thread(target=lambda: result.update(self.runner.start(self.payload)))
        thread.start()
        try:
            self.assertTrue(entered.wait(3))
            run_id = next(iter(self.runner.cancel_flags))
            ack = self.runner.cancel(run_id)
            self.assertTrue(ack['cancel_acknowledged'])
        finally:
            released.set()
            thread.join(4)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(self.runner.status(result['run_id'])['status'], 'cancelled')

    def setUp(self):
        # Reuse only the fixture setup, not the Codex provider test cases.
        fixtures.LocalRunnerTests.setUp(self)
        self.runner = OpenCodeRunner(self.root.parent / (self.root.name + "-runner"),
            self.root.parent / (self.root.name + "-skill-store"), self.source,
            max_model_turns=3, transport_factory=Backend)
        self.addCleanup(lambda: __import__("shutil").rmtree(self.runner.state, ignore_errors=True))
        self.payload = {"task": "Read skill", "model": "test/model", "effort": "default",
                        "skill_ref": {"skill_id": "sample", "revision_id": self.revision["revision_id"],
                                      "tree_hash": self.revision["tree_hash"]}}

    def test_fresh_restart_resume_and_evidence(self):
        run = self.runner.start(self.payload)
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["skills"][0]["use_evidence"], "native_skill_tool_completed")
        self.assertIsNone(run["usage"])
        restarted = OpenCodeRunner(self.runner.state, self.runner.store.root, self.source,
            max_model_turns=3, transport_factory=Backend)
        resumed = restarted.resume(run["run_id"], "Continue", expected_post_run_hash=run["post_run_hash"],
            expected_thread_id=run["thread_id"], model="test/model", effort="default")
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
        with self.assertRaisesRegex(RunnerError, "opencode_isolated_transport_required"):
            self.runner.start(self.payload)
        self.assertEqual(self.runner.preflight()["status"], "blocked")

    def test_running_tool_is_not_completed(self):
        with self.assertRaisesRegex(RunnerError, "opencode_outstanding_tool"):
            normalize_message({"info": {"role": "assistant", "time": {"completed": 1}},
                "parts": [{"type": "tool", "state": {"status": "running"}}]}, [])

    def test_multiple_skills_remain_pinned(self):
        second_source = self.root / "second-source"
        second_source.mkdir()
        (second_source / "SKILL.md").write_text("---\nname: second\n---\nUse amber.\n")
        second = self.runner.store.import_skill("second", second_source)
        refs = [self.payload["skill_ref"], {"skill_id": "second", "revision_id": second["revision_id"],
                                         "tree_hash": second["tree_hash"]}]
        payload = {key: value for key, value in self.payload.items() if key != "skill_ref"}
        run = self.runner.start({**payload, "skill_refs": refs})
        self.assertEqual(run["status"], "completed")
        self.assertEqual([item["skill_id"] for item in run["skills"]], ["sample", "second"])
        self.assertEqual(run["skills"][1]["use_evidence"], "offered")

    def test_resume_rejects_workspace_mutation(self):
        run = self.runner.start(self.payload)
        args = {"expected_post_run_hash": run["post_run_hash"], "expected_thread_id": run["thread_id"],
                "model": "test/model", "effort": "default"}
        (self.runner._run_dir(run["run_id"]) / "workspace/output.txt").write_text("changed")
        with self.assertRaisesRegex(RunnerError, "workspace_changed_since_snapshot"):
            self.runner.resume(run["run_id"], "Continue", **args)


if __name__ == "__main__":
    unittest.main()
