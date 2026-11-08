import unittest
from importlib.util import find_spec

if find_spec("lfx") is None:
    raise unittest.SkipTest("Optional lfx runtime is not installed")

from support.paths import repository_root
import tempfile
import asyncio
import importlib.util
import sys
from unittest.mock import patch
from lfx.schema import Data
from lfx.schema import Message

ROOT = repository_root()
from test_github.test_pull_requests.utils import create_case


class NativeGitHubPRTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.case = create_case(self.temp.name)
        spec = importlib.util.spec_from_file_location(
            "native_github_pr", ROOT / "components/laomedo/github_pr.py"
        )
        self.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.module
        spec.loader.exec_module(self.module)
        self.component = self.module.LaomedoGitHubPR()
        self.component.set(
            repository_url=self.case.url,
            labels=[],
            state="open",
            pr_choice="#1 Change 1",
        )

        def request(action, **body):
            return (
                self.case.gateway.discover(**body)
                if action == "discover"
                else self.case.gateway.execute(**body)
            )

        self.mock = patch.object(self.module, "pr_request", side_effect=request).start()
        self.addCleanup(patch.stopall)

    def test_outputs_share_execution_and_reference_drives_downstream(self):
        self.component.set(
            pr_context=Data(
                data={"action": "close", "request_id": "once", "grant_ref": "grant"}
            )
        )
        self.component._pre_run_setup()
        self.assertEqual(
            asyncio.run(self.component.context_output()).data["pr"]["state"], "closed"
        )
        self.assertEqual(
            asyncio.run(self.component.context_output()).data["operation"]["status"],
            "succeeded",
        )
        self.assertEqual(self.mock.call_count, 1)
        self.assertEqual(len(self.case.provider.writes), 1)

    def test_reference_conflict_never_dispatches(self):
        self.component.set(
            pr_context=Data(data={"pr": {"repository": "owner/repo", "number": 2}})
        )
        self.component._pre_run_setup()
        self.assertEqual(
            asyncio.run(self.component.context_output()).data["operation"][
                "error_category"
            ],
            "pr_reference_mismatch",
        )
        self.mock.assert_not_called()

    def test_normal_operation_accepts_message_json(self):
        self.component.set(
            pr_context=Message(
                text='{"action":"close","request_id":"message-once","grant_ref":"grant"}'
            )
        )
        self.component._pre_run_setup()
        self.assertEqual(
            asyncio.run(self.component.context_output()).data["operation"]["status"],
            "succeeded",
        )
        self.assertEqual(len(self.case.provider.writes), 1)

    def test_single_data_input_and_output_carry_current_snapshot_and_outcome(self):
        self.assertEqual(
            [
                i.name
                for i in self.component.inputs
                if i.to_dict().get("type") == "other"
            ],
            ["pr_context"],
        )
        self.assertEqual([o.name for o in self.component.outputs], ["pr"])
        result = asyncio.run(self.component.context_output()).data
        self.assertEqual(result["pr"]["number"], 1)
        self.assertEqual(result["operation"]["status"], "not_requested")
        self.assertIn("content_digest", result)

    def test_upstream_result_revalidates_identity_without_replaying_write(self):
        result = self.case.gateway.execute(self.case.url, [], "open", 1)
        result["operation"]["status"] = "succeeded"
        self.component.set(pr_context=Data(data=result), pr_choice="")
        self.assertEqual(
            asyncio.run(self.component.context_output()).data["pr"]["number"], 1
        )
        self.assertIsNone(self.mock.call_args.kwargs["operation"])
        self.assertEqual(self.case.provider.writes, [])

    def test_failed_or_unknown_upstream_stops_before_gateway(self):
        for status in ("failed", "unknown"):
            result = self.case.gateway.execute(self.case.url, [], "open", 1)
            result["operation"]["status"] = status
            self.component.set(pr_context=Data(data=result))
            self.component._pre_run_setup()
            output = asyncio.run(self.component.context_output()).data
            self.assertEqual(output["operation"]["status"], "failed")
            self.assertEqual(
                output["operation"]["error_category"], "pr_context_upstream_failed"
            )
        self.mock.assert_not_called()

    def test_malformed_explicit_operation_fields_are_not_dropped_to_allow_a_write(self):
        operation = {
            "action": "close",
            "request_id": "invalid-fields",
            "grant_ref": "grant",
        }
        for value in (
            {"operation": {**operation, "changes": None}},
            {"operation": operation, "content_digest": ""},
        ):
            self.component.set(pr_context=Data(data=value))
            self.component._pre_run_setup()
            result = asyncio.run(self.component.context_output()).data
            self.assertEqual(result["operation"]["status"], "failed")
            self.assertEqual(self.case.provider.writes, [])

    def test_filters_clear_selection_and_refresh_preserves_number(self):
        config = {item.name: item.to_dict() for item in self.component.inputs}
        config = asyncio.run(
            self.component.update_build_config(config, self.case.url, "repository_url")
        )
        self.assertEqual(len(config["pr_choice"]["options"]), 2)
        config = asyncio.run(
            self.component.update_build_config(
                config, ["research", "backend"], "labels"
            )
        )
        self.assertEqual(config["pr_choice"]["options"], ["#1 Change 1"])
        self.assertEqual(config["pr_choice"]["value"], "")
        config["pr_choice"]["value"] = "#1 Change 1"
        self.case.provider.prs[1]["title"] = "New title"
        config = asyncio.run(
            self.component.update_build_config(config, "#1 Change 1", "pr_choice")
        )
        self.assertEqual(config["pr_choice"]["value"], "#1 New title")

    def test_refresh_preserves_selection_and_separates_failure_from_empty(self):
        config = {item.name: item.to_dict() for item in self.component.inputs}
        config["repository_url"]["value"] = self.case.url
        config["state"]["value"] = "closed"
        config = asyncio.run(
            self.component.update_build_config(config, "closed", "state")
        )
        self.assertFalse(config["state"]["advanced"])
        self.assertIn("merged", config["state"]["options"])
        self.assertEqual(config["state"]["value"], "closed")
        self.mock.side_effect = ValueError("private provider details")
        config = asyncio.run(
            self.component.update_build_config(config, "closed", "state")
        )
        self.assertEqual(config["labels"]["options"], [])
        self.assertEqual(config["pr_choice"]["options"], [])
        self.assertEqual(
            config["discovery_status"]["value"],
            "GitHub discovery failed. Check connection and refresh.",
        )
        self.assertEqual(self.case.provider.writes, [])

    def test_failure_stops_task_and_unknown_is_routable(self):
        self.component.set(
            pr_context=Data(
                data={"action": "close", "request_id": "once", "grant_ref": "grant"}
            )
        )
        self.mock.side_effect = TimeoutError("dummy-secret")
        self.component._pre_run_setup()
        self.assertEqual(
            asyncio.run(self.component.context_output()).data["operation"]["status"],
            "unknown",
        )


if __name__ == "__main__":
    unittest.main()
