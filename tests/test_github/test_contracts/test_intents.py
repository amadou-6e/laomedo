"""Actual gateway journal preimages with isolated internal provider collaborators."""

from contextlib import closing
from hashlib import sha256
import json
import tempfile
import unittest
from laomedo.github.models import GitHubGrantBinding, GitHubOperationIntent
from test_github.test_issues.utils import create_case as create_issue_case
from test_github.test_pull_requests.utils import create_case as create_pr_case


class IntentHashTests(unittest.TestCase):
    def test_gateway_intent_hashes_preserve_request_identity_and_optional_changes(self):
        for kind, factory in (("issue", create_issue_case), ("pr", create_pr_case)):
            for action in ("modify", "close"):
                with (
                    self.subTest(kind=kind, action=action),
                    tempfile.TemporaryDirectory() as temporary,
                ):
                    case = factory(temporary)
                    operation = dict(
                        action=action, request_id="request_a", grant_ref="grant"
                    )
                    if action == "modify":
                        operation["changes"] = {"title": "Revue \u00e9", "body": ""}
                    case.gateway.execute(
                        case.url, ["research", "backend"], "open", 1, operation
                    )
                    with closing(case.store._connect()) as db:
                        authenticated = db.execute(
                            "SELECT grant_id,run_id FROM grants"
                        ).fetchone()
                        row = db.execute(
                            f"SELECT input_hash FROM {kind}_node_intents WHERE grant_ref=? AND request_id=?",
                            ("grant", "request_a"),
                        ).fetchone()
                    expected = dict(
                        repository="owner/repo",
                        number=1,
                        labels=["backend", "research"],
                        state="open",
                        operation=operation,
                        binding={
                            "grant_id": authenticated["grant_id"],
                            "run_id": authenticated["run_id"],
                        },
                    )
                    preimage = json.dumps(
                        expected,
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                    )
                    self.assertEqual(
                        row["input_hash"],
                        "sha256:" + sha256(preimage.encode()).hexdigest(),
                    )
                    model = GitHubOperationIntent(
                        **{
                            **expected,
                            "binding": GitHubGrantBinding(**expected["binding"]),
                        }
                    )
                    self.assertEqual(model.to_payload(), expected)
                    self.assertEqual(
                        set(model.to_payload()["operation"]),
                        (
                            {"action", "request_id", "grant_ref", "changes"}
                            if action == "modify"
                            else {"action", "request_id", "grant_ref"}
                        ),
                    )
