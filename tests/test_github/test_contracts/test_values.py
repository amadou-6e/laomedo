"""Wire/hash compatibility at the explicit strict model boundary."""

from hashlib import sha256
from copy import deepcopy
import json
import unittest

from pydantic import ValidationError
from laomedo.github.contract import issue_digest
from laomedo.github.contract import labels_value
from laomedo.github.contract import repository_from_url
from laomedo.github.contract import validate_repository
from laomedo.github.issues.contract import issue_value
from laomedo.github.issues.models import GitHubIssue
from laomedo.github.models import GitHubGrantBinding
from laomedo.github.models import GitHubOperationIntent
from laomedo.github.pull_requests.contract import pr_digest
from laomedo.github.pull_requests.contract import pr_value
from test_github.test_issues.utils import raw_issue
from test_github.test_pull_requests.utils import raw_pr


class GitHubValueTests(unittest.TestCase):
    def test_response_admission_keeps_public_codes_and_private_values_redacted(self):
        for prefix, project, raw in (
            ("issue", issue_value, raw_issue(1, ["backend"])),
            ("pr", pr_value, raw_pr(1, ["backend"])),
        ):
            for field, value in (("number", 2), ("title", []), ("state", "unknown")):
                with self.subTest(prefix=prefix, field=field):
                    invalid = deepcopy(raw)
                    invalid[field] = value
                    with self.assertRaisesRegex(
                        ValueError, f"^{prefix}_response_invalid$"
                    ):
                        project(invalid, "owner/repo", 1)
        normalized = issue_value(raw_issue(1, ["backend"]), "owner/repo", 1)
        with self.assertRaises(ValidationError) as caught:
            GitHubIssue(**{**normalized, "number": "private-invalid-value"})
        self.assertNotIn("private-invalid-value", str(caught.exception))

    def test_normalized_payload_order_and_unicode_hash_are_preserved(self):
        for project, raw, expected in (
            (
                issue_value,
                {**raw_issue(1, ["backend"]), "title": "Café λ", "body": None},
                {
                    "repository": "owner/repo",
                    "number": 1,
                    "url": "https://github.com/owner/repo/issues/1",
                    "node_id": "I_1",
                    "title": "Café λ",
                    "body": "",
                    "labels": ["backend"],
                    "state": "open",
                    "updated_at": "2026-10-13T00:00:00Z",
                },
            ),
            (
                pr_value,
                {**raw_pr(1, ["backend"]), "title": "Café λ", "body": None},
                {
                    "repository": "owner/repo",
                    "number": 1,
                    "url": "https://github.com/owner/repo/pull/1",
                    "node_id": "PR_1",
                    "title": "Café λ",
                    "body": "",
                    "labels": ["backend"],
                    "state": "open",
                    "draft": True,
                    "merged": False,
                    "updated_at": "2026-10-13T00:00:00Z",
                    "head": {
                        "repository": "owner/repo",
                        "branch": "demo",
                        "sha": "a" * 40,
                    },
                    "base": "main",
                },
            ),
        ):
            with self.subTest(project=project.__name__):
                result = project(raw, "owner/repo", 1)
                self.assertEqual(result, expected)
                self.assertEqual(list(result), list(expected))
                expected_digest = (
                    "sha256:"
                    + sha256(
                        json.dumps(
                            expected,
                            sort_keys=True,
                            separators=(",", ":"),
                            ensure_ascii=False,
                        ).encode()
                    ).hexdigest()
                )
                self.assertEqual(issue_digest(result), expected_digest)
                result["labels"].append("changed")
                self.assertEqual(raw["labels"], [{"name": "backend"}])
        self.assertIs(pr_digest, issue_digest)

    def test_pr_digest_keeps_the_literal_unicode_preimage(self):
        value = {"title": "\u03bb \u00e9", "labels": ["caf\u00e9"], "body": None}
        expected = (
            "sha256:"
            + sha256(
                '{"body":null,"labels":["caf\u00e9"],"title":"\u03bb \u00e9"}'.encode()
            ).hexdigest()
        )
        self.assertIs(pr_digest, issue_digest)
        self.assertEqual(pr_digest(value), expected)

    def test_all_six_intent_inputs_keep_the_exact_existing_hash_preimage(self):
        for operation in (
            {"action": "close", "request_id": "r", "grant_ref": "g"},
            {
                "action": "modify",
                "request_id": "r",
                "grant_ref": "g",
                "changes": {"title": "λ", "body": "", "labels": []},
            },
        ):
            expected = {
                "repository": "owner/repo",
                "number": 1,
                "labels": [],
                "state": "open",
                "operation": operation,
                "binding": {"grant_id": "grant", "run_id": "run"},
            }
            model = GitHubOperationIntent(
                **{**expected, "binding": GitHubGrantBinding(**expected["binding"])}
            )
            self.assertEqual(model.to_payload(), expected)
            self.assertEqual(issue_digest(model.to_payload()), issue_digest(expected))
            with self.assertRaises(ValidationError):
                GitHubGrantBinding(grant_id=1, run_id="run")

    def test_distinct_repository_admission_and_label_errors_remain_stable(self):
        self.assertEqual(validate_repository("Owner/RePo"), ("Owner", "RePo"))
        self.assertEqual(
            repository_from_url("https://github.com/Owner/RePo/"), "owner/repo"
        )
        with self.assertRaisesRegex(ValueError, "^Repository must be owner/name$"):
            validate_repository("owner/../repo")
        for value in (None, "http://github.com/o/r", "https://github.com/o/r?q=1"):
            with self.assertRaisesRegex(ValueError, "^repository_url_invalid$"):
                repository_from_url(value)
        labels = ["z", "é"]
        self.assertEqual(labels_value(labels), ["z", "é"])
        self.assertEqual(labels, ["z", "é"])
        for value in (["a", "a"], [""], "label"):
            with self.assertRaisesRegex(ValueError, "^labels_invalid$"):
                labels_value(value)
