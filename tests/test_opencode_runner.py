"""No credentials or model requests: verify OpenCode protocol and persistence."""

import unittest
import threading
import json

import test_local_runner as fixtures
from laomedo.opencode_runner import OpenCodeRunner, RunnerError, normalize_message, turn_parts
from laomedo.local_runner import _hash_tree, _json


from verification_runner import VerificationOpenCodeRunner as OpenCodeRunner


class Backend:
    sessions = 0
    histories = {}

    def __init__(self, workspace, evidence):
        self.workspace = workspace
        self.history = self.histories.setdefault(str(workspace),[])
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
        if path.endswith("/message") and method == "GET":
            return list(self.history)
        if path.endswith("/message"):
            (self.workspace / "output.txt").write_text("observed fixture")
            user_id = "user_" + str(len(self.history))
            self.history.append({"info":{"id":user_id,"sessionID":path.split("/")[2],"role":"user","time":{"created":1}},"parts":[{"type":"text","text":payload["parts"][0]["text"]}]})
            response = {"info": {"id": "msg_" + str(len(self.history)), "parentID":user_id, "role": "assistant", "time": {"created":1,"completed": 2},
                             "sessionID": path.split("/")[2], "providerID": "test", "modelID": "model"},
                    "parts": [{"type": "text", "text": "fixture answer"},
                              {"type": "tool", "tool": "skill", "callID": "tool1",
                               "state": {"status": "completed", "input": {"name": "sample"},
                                         "output": "skill body"}}]}
            self.history.append(response)
            return response
        raise AssertionError(path)

    def close(self):
        self.log.close()


class OpenCodeTests(unittest.TestCase):
    def test_inherited_handoff_validates_provenance_before_execution(self):
        from uuid import uuid4
        handoff = {"execution_id": str(uuid4()), "step": 0,
                   "source": {"provider": "opencode", "run_id": str(uuid4())},
                   "workspace_policy": "independent"}
        record = self.runner._prepare({**self.payload, "handoff": handoff})
        self.assertEqual(record["handoff"], handoff)
        handoff["step"] = -1
        self.assertEqual(record["handoff"]["step"], 0)
        with self.assertRaisesRegex(RunnerError, "invalid_handoff_provenance"):
            self.runner._prepare({**self.payload, "handoff": handoff})
        with self.assertRaisesRegex(RunnerError, "invalid_handoff_origin"):
            self.runner._prepare({**self.payload, "handoff": {
                **handoff, "step": 0, "source": {"provider": "foreign", "run_id": str(uuid4())}}})

    def test_run_waits_for_catalog_cleanup_without_overlapping_profiles(self):
        entered,released,attempted=threading.Event(),threading.Event(),threading.Event()
        waiting=threading.Event()
        class ObservedLock:
            def __init__(self):self.lock=threading.Lock()
            def acquire(self,*args,**kwargs):
                if kwargs.get('timeout')==30:waiting.set()
                return self.lock.acquire(*args,**kwargs)
            def release(self):self.lock.release()
            def __enter__(self):self.acquire();return self
            def __exit__(self,*args):self.release()
        self.runner._opencode_catalog_lock=ObservedLock()
        class PausedCatalog(Backend):
            def call(self,method,path,payload=None):
                if path=='/provider' and 'catalog' in str(self.workspace):
                    entered.set()
                    if not released.wait(45):raise TimeoutError()
                return super().call(method,path,payload)
        self.runner.transport_factory=PausedCatalog
        catalog_result={};run_result={};errors=[]
        def catalog():
            try:catalog_result.update(self.runner.model_catalog())
            except Exception as exc:errors.append(exc)
        def run():
            attempted.set()
            try:run_result.update(self.runner.start(self.payload))
            except Exception as exc:errors.append(exc)
        a=threading.Thread(target=catalog);b=threading.Thread(target=run)
        a.start()
        try:
            self.assertTrue(entered.wait(15));b.start();self.assertTrue(attempted.wait(15));self.assertTrue(waiting.wait(15))
            self.assertFalse(run_result)
        finally:
            released.set();a.join(20)
            if b.ident is not None:b.join(20)
        self.assertFalse(a.is_alive());self.assertFalse(b.is_alive());self.assertEqual(errors,[])
        self.assertEqual(run_result['status'],'completed')
        self.assertEqual(catalog_result['submitted_turns'],0)

    def test_exhausted_resume_preserves_completed_record_and_snapshot(self):
        run=self.runner.start(self.payload)
        self.runner.max_model_turns=1
        before=(self.runner._run_dir(run['run_id'])/'record.json').read_bytes()
        with self.assertRaisesRegex(RunnerError,'model_turn_cap_reached'):
            self.runner.resume(run['run_id'],'Continue',expected_post_run_hash=run['post_run_hash'],
                expected_thread_id=run['thread_id'],model='test/model',effort='default')
        self.assertEqual((self.runner._run_dir(run['run_id'])/'record.json').read_bytes(),before)
        self.assertFalse(self.runner.lock.locked())

    def test_catalog_refuses_shared_profile_access_while_runner_is_busy(self):
        self.runner.lock.acquire()
        try:
            with self.assertRaisesRegex(RunnerError,'runner_busy'):
                self.runner.model_catalog()
        finally:
            self.runner.lock.release()

    def test_catalog_only_reads_native_metadata_without_charging_turns(self):
        calls=[]
        class CatalogBackend(Backend):
            def call(self, method, path, payload=None):
                calls.append((method,path))
                return super().call(method,path,payload)
        self.runner.transport_factory=CatalogBackend
        result=self.runner.model_catalog()
        self.assertEqual(result,{'models':[{'id':'test/model','efforts':['default']}],'submitted_turns':0})
        self.assertEqual(self.runner.model_catalog(),result)
        self.assertEqual(calls,[('GET','/global/health'),('GET','/provider')])
        self.assertFalse((self.runner.state/'turn-ledger.json').exists())
        self.assertEqual(list((self.runner.state/'catalog').iterdir()),[])

    def test_empty_skill_set_is_valid_and_unselected_files_are_still_rejected(self):
        payload={key:value for key,value in self.payload.items() if key!='skill_ref'}
        payload['skill_refs']=[]
        record=self.runner._prepare(payload)
        root=self.runner._run_dir(record['run_id'])/'workspace'
        self.runner._verify_pinned_skills(root,record)
        (root/'.agents/skills/unselected').mkdir()
        with self.assertRaisesRegex(RunnerError,'pinned_skill_workspace_changed'):
            self.runner._verify_pinned_skills(root,record)

    def test_cancel_before_session_does_not_submit_or_charge(self):
        entered, released = threading.Event(), threading.Event()
        class PausingBackend(Backend):
            def call(self, method, path, payload=None):
                if path == '/provider':
                    entered.set()
                    self_waited = released.wait(45)
                    if not self_waited:
                        raise TimeoutError()
                return super().call(method, path, payload)
        self.runner.transport_factory = PausingBackend
        result = {}
        thread = threading.Thread(target=lambda: result.update(self.runner.start(self.payload)))
        thread.start()
        try:
            self.assertTrue(entered.wait(15))
            run_id = next(iter(self.runner.cancel_flags))
            response = self.runner.cancel(run_id)
            self.assertTrue(response['cancel_requested'])
            self.assertFalse(response['cancel_acknowledged'])
        finally:
            released.set()
            thread.join(20)
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
            if not released.wait(45):
                raise TimeoutError()
            return attempt
        self.runner._reserve_turn = pause_reservation
        result = {}
        thread = threading.Thread(target=lambda: result.update(self.runner.start(self.payload)))
        thread.start()
        try:
            self.assertTrue(reserved.wait(15))
            run_id = next(iter(self.runner.cancel_flags))
            self.assertTrue(self.runner.cancel(run_id)['cancel_requested'])
        finally:
            released.set()
            thread.join(20)
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
                    if not released.wait(30):
                        raise TimeoutError()
                    return {'info': {}, 'parts': []}
                return super().call(method, path, payload)
        self.runner.transport_factory = AbortedBackend
        result = {}
        thread = threading.Thread(target=lambda: result.update(self.runner.start(self.payload)))
        thread.start()
        try:
            self.assertTrue(entered.wait(15))
            run_id = next(iter(self.runner.cancel_flags))
            ack = self.runner.cancel(run_id)
            self.assertTrue(ack['cancel_acknowledged'])
        finally:
            released.set()
            thread.join(20)
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


    def test_async_start_uses_opencode_identity_and_cancel_before_dispatch_costs_no_turn(self):
        from uuid import uuid4
        gate = threading.Event()
        record = self.runner.start_async({**self.payload,"request_id":str(uuid4())},response_gate=gate)
        self.assertEqual(record["provider"],"opencode")
        cancelled = self.runner.cancel(record["run_id"])
        self.assertTrue(cancelled["cancel_confirmed"])
        gate.set()
        self.assertEqual(self.runner.status(record["run_id"])["status"],"cancelled")
        self.assertFalse((self.runner.state / "turn-ledger.json").exists())

    def test_resume_activity_contains_only_new_native_messages(self):
        from uuid import uuid4
        first = self.runner.start(self.payload)
        root = self.runner._run_dir(first["run_id"])
        initial = json.loads((root/"activity-attempts"/(first["activity_initial_attempt_id"]+".json")).read_text())
        selected = str(uuid4())
        second = self.runner.resume(first["run_id"],"New turn",expected_post_run_hash=first["post_run_hash"],
            expected_thread_id=first["thread_id"],model="test/model",effort="default",activity_attempt_id=selected)
        self.assertTrue(second["attempt_finished"])
        self.assertTrue(second["snapshot_ready"])
        attempt = json.loads((root/"activity-attempts"/(selected+".json")).read_text())
        self.assertEqual(attempt["native_start"],initial["native_end"])
        from laomedo.runner_activity import read_feed
        events=read_feed(root/"activity-events.jsonl",after=attempt["native_start"],before=attempt["native_end"])["events"]
        texts=[part["text"] for event in events for message in event["event"]["params"]["messages"]
               for part in message["parts"] if part.get("type")=="text"]
        self.assertIn("New turn",texts)
        self.assertNotIn("Read skill",texts)
        with self.assertRaisesRegex(RunnerError,"activity_attempt_already_exists"):
            self.runner.resume(first["run_id"],"Replay",expected_post_run_hash=second["post_run_hash"],
                expected_thread_id=first["thread_id"],model="test/model",effort="default",activity_attempt_id=selected)

    def test_otel_attempt_boundaries_isolate_resume_feed(self):
        from unittest.mock import patch
        from uuid import uuid4
        from laomedo.runner_activity import read_feed, receipt
        def export(root, start, session, model):
            with (root/'otel-events.jsonl').open('a') as stream:
                stream.write(json.dumps(receipt({'method':'otel/record','params':{'attributes':{'conversation.id':session},'marker':start}}))+'\n')
            return True
        with patch('laomedo.opencode_telemetry.export_attempt', side_effect=export):
            first=self.runner.start(self.payload)
            root=self.runner._run_dir(first['run_id'])
            initial=json.loads((root/'activity-attempts'/(first['activity_initial_attempt_id']+'.json')).read_text())
            selected=str(uuid4())
            self.runner.resume(first['run_id'],'Second turn',expected_post_run_hash=first['post_run_hash'],expected_thread_id=first['thread_id'],model='test/model',effort='default',activity_attempt_id=selected)
            second=json.loads((root/'activity-attempts'/(selected+'.json')).read_text())
        self.assertEqual((initial['otel_start'],initial['otel_end']),(0,1))
        self.assertEqual((second['otel_start'],second['otel_end']),(1,2))
        events=read_feed(root/'otel-events.jsonl',after=second['otel_start'],before=second['otel_end'])['events']
        self.assertEqual(len(events),1)
        self.assertEqual(events[0]['event']['params']['marker'],second['native_start'])

    def test_snapshot_capture_failure_does_not_change_execution_success(self):
        from unittest.mock import patch
        with patch('laomedo.opencode_activity.retain_messages',side_effect=OSError('capture unavailable')):
            result=self.runner.start(self.payload)
        self.assertEqual(result['status'],'completed')
        self.assertTrue(result['snapshot_ready'])
        attempt=json.loads((self.runner._run_dir(result['run_id'])/'activity-attempts'/(result['activity_initial_attempt_id']+'.json')).read_text())
        self.assertEqual(attempt['capture_error'],'opencode_native_snapshot_unavailable')

    def test_async_variant_rejected_before_workspace_preparation(self):
        from uuid import uuid4
        with self.assertRaisesRegex(RunnerError,"unsupported_opencode_effort"):
            self.runner.start_async({**self.payload,"effort":"high","request_id":str(uuid4())})
        self.assertEqual(list((self.runner.state/"runs").iterdir()),[])

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
