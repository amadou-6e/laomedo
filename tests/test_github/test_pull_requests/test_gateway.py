"""Gateway regression controls with internal provider doubles."""

import json
import tempfile
import unittest
from laomedo.github.pull_requests.gateway import GitHubPRGateway
from laomedo.host.mediation.errors import MediationError

from test_github.test_pull_requests.utils import create_case, raw_pr


class LiveGitHubPRTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.case = create_case(self.temp.name)

    def execute(
        self, action="modify", changes=None, request_id="effect", number=1, ref="grant"
    ):
        operation = {"action": action, "request_id": request_id, "grant_ref": ref}
        if action == "modify":
            operation["changes"] = changes or {"title": "Updated title"}
        return self.case.gateway.execute(self.case.url, [], "open", number, operation)

    def test_discovery_matches_all_labels_and_state(self):
        self.assertEqual(
            [
                x["number"]
                for x in self.case.gateway.discover(
                    self.case.url, ["research", "backend"]
                )["prs"]
            ],
            [1],
        )
        self.assertEqual(
            len(self.case.gateway.discover(self.case.url, [], "all")["prs"]), 3
        )

    def test_refresh_reads_current_content_and_refuses_stale_filters(self):
        self.case.provider.prs[1]["body"] = "Changed"
        self.assertEqual(
            self.case.gateway.execute(self.case.url, [], "open", 1)["pr"]["body"],
            "Changed",
        )
        with self.assertRaisesRegex(ValueError, "no_longer_matches"):
            self.case.gateway.execute(self.case.url, ["backend"], "open", 2)

    def test_modify_and_restart_replay_send_once(self):
        first = self.execute(
            changes={"title": "Updated title", "body": "", "labels": []}
        )
        self.assertEqual(first["operation"]["status"], "succeeded")
        self.assertEqual(first["pr"]["labels"], [])
        self.assertEqual(first["pr"]["body"], "")
        self.case.gateway = GitHubPRGateway(
            {"owner/repo": self.case.transport},
            self.case.store,
            lambda _: self.case.binding,
        )
        self.assertEqual(
            self.execute(changes={"title": "Updated title", "body": "", "labels": []}),
            first,
        )
        self.assertEqual(len(self.case.provider.writes), 2)
        with self.assertRaisesRegex(ValueError, "operation_conflict"):
            self.execute(changes={"title": "Other"})

    def test_close_returns_confirmed_pr_outside_original_filter(self):
        result = self.execute("close")
        self.assertEqual(result["operation"]["status"], "succeeded")
        self.assertEqual(result["pr"]["state"], "closed")
        self.assertEqual(self.execute("close"), result)
        self.assertEqual(len(self.case.provider.writes), 1)

    def test_timeout_retains_unknown_without_resending(self):
        self.case.provider.timeout_after_write = True
        result = self.execute()
        self.assertEqual(result["operation"]["status"], "unknown")
        self.assertEqual(self.execute(), result)
        self.assertEqual(len(self.case.provider.writes), 1)
        self.assertNotIn("dummy-secret", json.dumps(result))

    def test_partial_metadata_labels_operation_stays_unknown(self):
        self.case.provider.reject_labels = True
        result = self.execute(changes={"title": "Changed", "labels": []})
        self.assertEqual(result["operation"]["status"], "unknown")
        self.assertEqual(
            self.execute(changes={"title": "Changed", "labels": []}), result
        )
        self.assertEqual(len(self.case.provider.writes), 1)

    def test_expired_revoked_foreign_target_and_grant(self):
        self.case.clock[0] = 200
        self.assertEqual(self.execute()["operation"]["status"], "failed")
        self.case.clock[0] = 100
        self.assertEqual(
            self.execute(number=2, request_id="other")["operation"]["status"], "failed"
        )
        with self.assertRaisesRegex(ValueError, "grant_unavailable"):
            self.execute(ref="foreign")
        self.case.store.revoke_run("run")
        self.assertEqual(
            self.execute(request_id="revoked")["operation"]["status"], "failed"
        )
        self.assertEqual(self.case.provider.writes, [])

    def test_fork_merged_changed_branch_and_changed_head_refused(self):
        for mutate in (
            lambda pr: pr["head"]["repo"].update(full_name="foreign/fork"),
            lambda pr: pr.update(merged_at="now"),
            lambda pr: pr["head"].update(ref="other"),
        ):
            self.case.provider.prs[1] = raw_pr(1, ["backend"])
            mutate(self.case.provider.prs[1])
            self.assertEqual(
                self.execute(
                    request_id=str(len(json.dumps(self.case.provider.prs[1])))
                )["operation"]["status"],
                "failed",
            )
        self.assertEqual(self.case.provider.writes, [])

    def test_expiry_between_read_and_write_is_rechecked(self):
        def expire(_):
            self.case.clock[0] = 200

        self.case.provider.before_read = expire
        self.assertEqual(self.execute()["operation"]["status"], "failed")
        self.assertEqual(self.case.provider.writes, [])

    def test_incomplete_discovery_is_refused(self):
        self.case.provider.full_pages = True
        with self.assertRaisesRegex(ValueError, "discovery_incomplete"):
            self.case.gateway.discover(self.case.url, [])

    def test_missing_target_grant_cannot_be_created(self):
        with self.assertRaises(MediationError):
            self.case.store.issue(
                run_id="x",
                invocation_id="x",
                repository="owner/repo",
                operations={"pr_node_update"},
                branch="demo",
                ttl_seconds=60,
            )

    def test_payload_target_override_and_merge_action_refused(self):
        for operation in (
            {"action": "merge", "request_id": "x", "grant_ref": "grant"},
            {"action": "close", "request_id": "x", "grant_ref": "grant", "number": 2},
        ):
            with self.assertRaisesRegex(ValueError, "operation_invalid"):
                self.case.gateway.execute(self.case.url, [], "open", 1, operation)
        self.assertEqual(self.case.provider.writes, [])
