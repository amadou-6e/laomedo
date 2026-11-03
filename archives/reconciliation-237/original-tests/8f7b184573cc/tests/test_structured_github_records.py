"""Internal baseline compatibility controls; no live provider acceptance."""

import copy
import json
from pathlib import Path
import unittest
from pydantic import ValidationError
from laomedo.github.issues.contract import issue_value
from laomedo.github.contract import issue_digest
from laomedo.github.issues.models import GitHubIssue
from laomedo.github.pull_requests.contract import pr_value


class StructuredGitHubRecordsTests(unittest.TestCase):
    def test_pre_refactor_payloads_and_digest_preimages(self):
        cases = json.loads(
            (
                Path(__file__).parent / "contracts/structured-data-a9317f6.json"
            ).read_text(encoding="utf-8")
        )
        for key, case in cases.items():
            if not key.startswith(("issue:", "pr:")):
                continue
            with self.subTest(case=key):
                project = issue_value if key.startswith("issue:") else pr_value
                result = project(case["raw"], "owner/repo", 1)
                self.assertEqual(result, case["normalized"])
                self.assertEqual(list(result), list(case["normalized"]))
                self.assertEqual(issue_digest(result), case["digest"])
                result["labels"].append("changed")
                self.assertNotIn("changed", [v["name"] for v in case["raw"]["labels"]])

    def test_admission_preserves_public_errors_and_strict_internal_model(self):
        cases = json.loads(
            (
                Path(__file__).parent / "contracts/structured-data-a9317f6.json"
            ).read_text(encoding="utf-8")
        )
        for prefix, project in (("issue", issue_value), ("pr", pr_value)):
            case = cases[f"{prefix}:None"]
            for field, value in (("number", 2), ("title", []), ("state", "unknown")):
                raw = copy.deepcopy(case["raw"])
                raw[field] = value
                with self.assertRaisesRegex(ValueError, f"{prefix}_response_invalid"):
                    project(raw, "owner/repo", 1)
        with self.assertRaises(ValidationError) as caught:
            GitHubIssue(
                **{
                    **cases["issue:None"]["normalized"],
                    "number": "private-invalid-value",
                }
            )
        self.assertNotIn("private-invalid-value", str(caught.exception))
