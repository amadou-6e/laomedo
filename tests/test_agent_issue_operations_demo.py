import contextlib,importlib.util,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from test_live_github_issue import FakeGitHub,raw_issue
from laomedo.github_rest_transport import GitHubRestTransport

ROOT=Path(__file__).resolve().parents[1]
class AgentIssueDemoTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location("operation_demo",ROOT/"examples/github-issue/agent_operation_demo.py")
        self.demo=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.demo)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.fake=FakeGitHub();self.fake.issues={12:raw_issue(12,["bug"]),15:raw_issue(15,[])}
        self.rest=GitHubRestTransport("owner/repo",lambda connection_id=None,connection_generation=None:"dummy",opener=self.fake)
        self.config={"campaign_id":"campaign","issues":{str(n):self.rest("owner/repo","issue_read",{"number":n}) for n in (12,15)},
            "approved":{"modify":{"number":15,"changes":{"title":"Filter demo: agent updated","body":"approved body","labels":["question"]}},"close":{"number":12}}}
        # Fake catalog must advertise the approved question label.
        original=self.fake.open
        def opener(call,timeout=15):
            if call.full_url.split('?')[0].endswith('/labels'):
                class Response:
                    def __enter__(self):return self
                    def __exit__(self,*_):pass
                    def read(self,limit):return b'[{"name":"question"}]'[:limit]
                return Response()
            return original(call,timeout)
        self.fake.open=opener
        self.record={"run_id":"native-run","status":"completed","evidence_complete":True,"completion_basis":"native_trace_closure","snapshot_ready":True,
            "answer":json.dumps({"task_outcome":"success","operations":self.config["approved"]})}
        self.demo.save(self.root/"config.json",self.config);self.demo.save(self.root/"agent-result.json",self.record)
        provider=type("Provider",(),{"current":staticmethod(lambda *_:True)})()
        self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(self.demo,"REPOSITORY","owner/repo"));self.stack.enter_context(patch.object(self.demo,"connection",return_value=provider));self.stack.enter_context(patch.object(self.demo,"transport",return_value=self.rest))
    def apply(self):
        with contextlib.redirect_stdout(io.StringIO()):return self.demo.apply(self.root)
    def test_only_exact_native_completed_output_is_accepted(self):
        self.demo.accepted_plan(self.config,self.record)
        for field,value in (("status","unknown"),("evidence_complete",False),("completion_basis","process_exit"),("snapshot_ready",False)):
            with self.assertRaises(ValueError):self.demo.accepted_plan(self.config,{**self.record,field:value})
        with self.assertRaises(ValueError):self.demo.accepted_plan(self.config,{**self.record,"answer":'{"task_outcome":"success","operations":{}}'})
    def test_update_then_close_confirmed_and_replay_has_no_new_effect(self):
        self.apply();self.assertEqual(self.fake.patch_count,2);self.assertEqual(self.fake.issues[15]["title"],"Filter demo: agent updated");self.assertEqual(self.fake.issues[12]["state"],"closed")
        self.apply();self.assertEqual(self.fake.patch_count,2)
    def test_source_change_refuses_before_grant_or_effect(self):
        self.fake.issues[15]["body"]="changed"
        with self.assertRaisesRegex(ValueError,"issue_changed"):self.apply()
        self.assertEqual(self.fake.patch_count,0);self.assertFalse((self.root/"binding.json").exists())
    def test_unknown_update_never_advances_to_close_or_retries(self):
        self.fake.timeout_after_write=True
        with self.assertRaisesRegex(ValueError,"operation_not_confirmed"):self.apply()
        self.assertEqual(self.fake.patch_count,1);self.assertEqual(self.fake.issues[12]["state"],"open")
        with self.assertRaises(ValueError):self.apply()
        self.assertEqual(self.fake.patch_count,1)
