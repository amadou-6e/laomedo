"""Internal controls for host-owned feedback identities; no live provider calls."""

import tempfile
import json


import unittest
from contextlib import closing
from unittest.mock import patch
from laomedo.github.pull_requests.gateway import GitHubPRGateway
from test_github.test_pull_requests.utils import create_case


class FeedbackIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.case = create_case(self.temp.name)

    def prepare(self, number=1):
        self.case.gateway.feedback_grants = {"owner/repo#1": "grant"}
        current = self.case.gateway.execute(self.case.url, [], "open", number)
        return self.case.gateway.prepare_feedback(
            self.case.url, [], "open", number, current["content_digest"]
        )["ticket"]

    def apply(self, ticket, operation=None):
        return self.case.gateway.apply_feedback(
            ticket,
            operation or {"action": "modify", "changes": {"body": "Agent proposal"}},
        )

    def test_identity_is_host_generated_and_not_returned_to_agent(self):
        ticket = self.prepare()
        with closing(self.case.store._connect()) as db:
            row = db.execute(
                "SELECT * FROM pr_feedback_tickets WHERE ticket=?", (ticket,)
            ).fetchone()
        self.assertTrue(row["request_id"].startswith("pr-feedback-"))
        self.assertEqual(row["grant_ref"], "grant")
        self.assertEqual(self.apply(ticket)["operation"]["status"], "succeeded")
        self.assertEqual(len(self.case.provider.writes), 1)

    def test_model_cannot_supply_identity_capability_or_target(self):
        ticket = self.prepare()
        for field in ("request_id", "grant_ref", "repository", "pr_number", "expected"):
            with self.assertRaisesRegex(ValueError, "pr_operation_invalid"):
                self.apply(ticket, {"action": "close", field: "model-chosen"})
        self.assertEqual(len(self.case.provider.writes), 0)

    def test_missing_scope_refuses_before_model_can_be_started(self):
        current = self.case.gateway.execute(self.case.url, [], "open", 1)
        with self.assertRaisesRegex(ValueError, "pr_feedback_not_configured"):
            self.case.gateway.prepare_feedback(
                self.case.url, [], "open", 1, current["content_digest"]
            )

    def test_same_ticket_same_proposal_replays_one_effect(self):
        ticket = self.prepare()
        self.assertEqual(self.apply(ticket), self.apply(ticket))
        self.assertEqual(len(self.case.provider.writes), 1)

    def test_same_ticket_different_proposal_conflicts(self):
        ticket = self.prepare()
        self.apply(ticket)
        with self.assertRaisesRegex(ValueError, "pr_operation_conflict"):
            self.apply(ticket, {"action": "modify", "changes": {"body": "Different"}})
        self.assertEqual(len(self.case.provider.writes), 1)

    def test_unknown_effect_is_not_retried(self):
        ticket = self.prepare()
        self.case.provider.timeout_after_write = True
        self.assertEqual(self.apply(ticket)["operation"]["status"], "unknown")
        self.assertEqual(self.apply(ticket)["operation"]["status"], "unknown")
        self.assertEqual(len(self.case.provider.writes), 1)

    def test_changed_pr_after_prepare_is_refused(self):
        ticket = self.prepare()
        self.case.provider.prs[1]["body"] = "Human edit"
        with self.assertRaisesRegex(ValueError, "pr_changed_since_agent_read"):
            self.apply(ticket)
        self.assertEqual(len(self.case.provider.writes), 0)

    def test_expired_or_unknown_ticket_refused(self):
        ticket = self.prepare()
        with closing(self.case.store._connect()) as db, db:
            db.execute("UPDATE pr_feedback_tickets SET expires=0")
        for value in (ticket, "0" * 64, "invalid"):
            with self.assertRaisesRegex(ValueError, "pr_feedback_ticket_invalid"):
                self.apply(value)
        self.assertEqual(len(self.case.provider.writes), 0)

    def test_grant_rotation_does_not_rebind_existing_ticket(self):
        ticket = self.prepare()
        _, token = self.case.store.issue(
            run_id="new",
            invocation_id="new",
            repository="owner/repo",
            operations={"pr_node_update"},
            target_prs={1: "main"},
            branch="demo",
            ttl_seconds=60,
        )
        self.case.binding = {
            "token": token,
            "run_id": "new",
            "repository": "owner/repo",
        }
        with self.assertRaisesRegex(ValueError, "pr_grant_unavailable"):
            self.apply(ticket)
        self.assertEqual(len(self.case.provider.writes), 0)

    def test_revoked_grant_cannot_apply_reserved_ticket(self):
        ticket = self.prepare()
        with closing(self.case.store._connect()) as db, db:
            db.execute("UPDATE grants SET revoked_at=1")
        with self.assertRaisesRegex(ValueError, "pr_grant_unavailable"):
            self.apply(ticket)
        self.assertEqual(len(self.case.provider.writes), 0)

    def test_disabled_host_configuration_invalidates_reserved_ticket(self):
        ticket = self.prepare()
        self.case.gateway.feedback_grants = {}
        with self.assertRaisesRegex(ValueError, "pr_feedback_not_configured"):
            self.apply(ticket)
        self.assertEqual(len(self.case.provider.writes), 0)

    def test_clock_rollback_cannot_extend_ticket_lifetime(self):
        ticket = self.prepare()
        issued = self.case.store.monotonic()
        with (
            patch.object(
                self.case.store, "now", return_value=self.case.store.now() - 10000
            ),
            patch.object(self.case.store, "monotonic", return_value=issued + 301),
        ):
            with self.assertRaisesRegex(ValueError, "pr_feedback_ticket_invalid"):
                self.apply(ticket)
        self.assertEqual(len(self.case.provider.writes), 0)

    def test_monotonic_clock_reset_refuses_ticket(self):
        ticket = self.prepare()
        with patch.object(self.case.store, "monotonic", return_value=0):
            with self.assertRaisesRegex(ValueError, "pr_feedback_ticket_invalid"):
                self.apply(ticket)
        self.assertEqual(len(self.case.provider.writes), 0)

    def test_restart_preserves_ticket_identity_and_replay(self):
        ticket = self.prepare()
        first = self.apply(ticket)
        restarted = GitHubPRGateway(
            {"owner/repo": self.case.transport},
            self.case.store,
            self.case.gateway.grant_resolver,
            feedback_grants={"owner/repo#1": "grant"},
        )
        self.assertEqual(
            restarted.apply_feedback(
                ticket, {"action": "modify", "changes": {"body": "Agent proposal"}}
            ),
            first,
        )
        self.assertEqual(len(self.case.provider.writes), 1)

    def test_wrong_branch_or_target_refused_at_prepare(self):
        self.case.gateway.feedback_grants = {"owner/repo#2": "grant"}
        current = self.case.gateway.execute(self.case.url, [], "open", 2)
        with self.assertRaisesRegex(ValueError, "pr_grant_unavailable"):
            self.case.gateway.prepare_feedback(
                self.case.url, [], "open", 2, current["content_digest"]
            )
        self.assertEqual(len(self.case.provider.writes), 0)

    def test_feedback_snapshot_keeps_original_labels_extensions_and_deadlines(self):
        case = self.case
        original = case.transport

        def extended_transport(repository, operation, payload):
            value = original(repository, operation, payload)
            return (
                {
                    **value,
                    "provider_extension": {"nullable": None, "checks": ["é", False]},
                }
                if operation == "pr_node_read"
                else value
            )

        case.gateway.transports["owner/repo"] = extended_transport
        case.gateway.feedback_grants = {"owner/repo#1": "grant"}
        labels = ["research", "backend"]
        selected = case.gateway.execute(case.url, labels, "open", 1)
        issued = case.store.monotonic()
        with patch.object(case.store, "monotonic", return_value=issued):
            ticket = case.gateway.prepare_feedback(
                case.url, labels, "open", 1, selected["content_digest"]
            )["ticket"]
        with closing(case.store._connect()) as db:
            row = db.execute(
                "SELECT * FROM pr_feedback_tickets WHERE ticket=?", (ticket,)
            ).fetchone()
        expected = dict(
            repository_url=case.url,
            labels=labels,
            state="open",
            pr_number=1,
            expected=selected["content_digest"],
            pr=selected["pr"],
            issued_monotonic=issued,
            expires_monotonic=issued + 300,
        )
        self.assertEqual(json.loads(row["context"]), expected)
        self.assertEqual(list(json.loads(row["context"])), list(expected))
        self.assertEqual(row["expires"], 400)
        self.assertEqual(row["grant_ref"], "grant")
        self.assertTrue(row["request_id"].startswith("pr-feedback-"))
        for wall, monotonic in (
            (100, issued - 1),
            (100, issued + 300),
            (400, issued + 1),
        ):
            with (
                self.subTest(wall=wall, monotonic=monotonic),
                patch.object(case.store, "now", return_value=wall),
                patch.object(case.store, "monotonic", return_value=monotonic),
            ):
                with self.assertRaisesRegex(ValueError, "^pr_feedback_ticket_invalid$"):
                    case.gateway.apply_feedback(ticket, {"action": "close"})
        self.assertEqual(case.provider.writes, [])
