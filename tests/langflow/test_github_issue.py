import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from lfx.schema import Data
from laomedo.github_issue_gateway import GitHubIssueGateway
from laomedo.github_mediation import MediationStore
from laomedo.github_rest_transport import GitHubRestTransport

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
from test_live_github_issue import FakeGitHub


class NativeGitHubIssueTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("native_github_issue", ROOT / "components/laomedo/github_issue.py")
        self.module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = self.module; spec.loader.exec_module(self.module)
        self.component = self.module.LaomedoGitHubIssue()
        self.component.set(repository_url="https://github.com/owner/repo", labels=[], state="open", issue_choice="#1 Task 1")
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.store = MediationStore(Path(self.temp.name) / "mediation.db")
        _, token = self.store.issue(run_id="run", invocation_id="invoke", repository="owner/repo", operations={"issue_update"}, target_issues={1}, ttl_seconds=60)
        self.fake = FakeGitHub(); transport = GitHubRestTransport("owner/repo", lambda: "DUMMY-PROVIDER-TOKEN", opener=self.fake)
        self.gateway = GitHubIssueGateway({"owner/repo":transport}, self.store, lambda _: {"token":token,"run_id":"run","repository":"owner/repo"})
        def request(action, **body):
            return self.gateway.discover(**body) if action == "discover" else self.gateway.execute(**body)
        self.mock = patch.object(self.module, "issue_request", side_effect=request).start()
        self.addCleanup(patch.stopall)
    def test_outputs_share_one_live_read(self):
        self.component._pre_run_setup()
        self.assertEqual(self.component.issue_output().data["number"], 1)
        self.assertIn("Current issue body", self.component.task_output().text)
        self.assertEqual(self.component.result_output().data["operation"]["status"], "not_requested")
        self.assertEqual(self.mock.call_count, 1)
    def test_each_build_fetches_current_content(self):
        self.component._pre_run_setup(); self.component.issue_output()
        self.fake.issues[1]["body"] = "Latest body"
        self.component._pre_run_setup()
        self.assertEqual(self.component.issue_output().data["body"], "Latest body")
        self.assertEqual(self.mock.call_count, 2)
    def test_close_from_incoming_data_has_one_effect(self):
        self.component.set(operation=Data(data={"action":"close","request_id":"close-once","grant_ref":"grant"}))
        self.component._pre_run_setup()
        self.assertEqual(self.component.issue_output().data["state"], "closed")
        self.assertEqual(self.component.result_output().data["operation"]["status"], "succeeded")
        self.component.task_output()
        self.assertEqual(self.fake.patch_count, 1)
    def test_label_update_filters_all_labels(self):
        config = {item.name:item.to_dict() for item in self.component.inputs}
        config = asyncio.run(self.component.update_build_config(config,"https://github.com/owner/repo","repository_url"))
        self.assertEqual(len(config["issue_choice"]["options"]),3)
        config = asyncio.run(self.component.update_build_config(config,["research","backend"],"labels"))
        self.assertEqual(config["issue_choice"]["options"],["#1 Task 1"])
        self.assertEqual(config["issue_choice"]["value"], "")
        self.assertFalse(config["labels"]["combobox"])
    def test_reference_cannot_override_explicit_selection(self):
        self.component.set(issue_reference=Data(data={"repository":"owner/repo","number":2}))
        self.component._pre_run_setup()
        result = self.component.result_output().data
        self.assertEqual(result["operation"]["error_category"],"issue_reference_mismatch")
        self.assertEqual(self.mock.call_count,0)
    def test_missing_selection_is_routable_without_agent_call(self):
        self.component.set(issue_choice="")
        self.component._pre_run_setup()
        self.assertEqual(self.component.result_output().data["operation"]["error_category"],"selected_issue_required")
        self.assertEqual(self.mock.call_count,0)

    def test_refresh_updates_title_without_losing_issue_identity(self):
        config = {item.name:item.to_dict() for item in self.component.inputs}
        config["repository_url"]["value"] = "https://github.com/owner/repo"
        config["issue_choice"]["value"] = "#1 Task 1"
        self.fake.issues[1]["title"] = "New title"
        config = asyncio.run(self.component.update_build_config(config,"#1 Task 1","issue_choice"))
        self.assertEqual(config["issue_choice"]["value"],"#1 New title")

    def test_failed_read_does_not_emit_a_task_prompt(self):
        self.component.set(issue_choice="")
        self.component._pre_run_setup()
        self.assertEqual(self.component.task_output().text, "")
        self.assertEqual(self.component.result_output().data["operation"]["status"], "failed")
