"""Cover the GitHub public error boundary after interface relocation."""

import ast
import json
import unittest

from support.paths import repository_root, error_catalogue_path
from laomedo.github.issues.contract import ERROR_CODES as ISSUE_CODES
from laomedo.github.pull_requests.contract import ERROR_CODES as PR_CODES


class GitHubErrorCatalogueTests(unittest.TestCase):
    def test_literal_handler_failures_are_catalogued(self):
        root = repository_root()
        catalogue = json.loads((error_catalogue_path()).read_text(encoding="utf-8"))
        for feature in ("issues", "pull_requests"):
            path = root / "src/laomedo/github/interface" / feature / "handler.py"
            tree = ast.parse(path.read_text(encoding="utf-8"))
            codes = {
                value.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Dict)
                for key, value in zip(node.keys, node.values)
                if isinstance(key, ast.Constant)
                and key.value == "error_category"
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)
            }
            self.assertTrue(codes, path)
            self.assertFalse(codes - catalogue.keys(), (path, codes - catalogue.keys()))
            for code in codes:
                for field in ("title", "description", "recovery"):
                    self.assertTrue(catalogue[code][field].strip(), (code, field))

    def test_public_contract_and_component_codes_have_descriptive_catalogue_entries(
        self,
    ):
        root = repository_root()
        catalogue = json.loads((error_catalogue_path()).read_text(encoding="utf-8"))
        codes = set(ISSUE_CODES | PR_CODES)
        for feature in ("github_issue", "github_pr"):
            tree = ast.parse(
                (root / "components/laomedo" / (feature + ".py")).read_text()
            )
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Raise)
                    and isinstance(node.exc, ast.Call)
                    and node.exc.args
                    and isinstance(node.exc.args[0], ast.Constant)
                    and isinstance(node.exc.args[0].value, str)
                ):
                    codes.add(node.exc.args[0].value)
        self.assertFalse(codes - catalogue.keys())
        for code in codes:
            with self.subTest(code=code):
                for field in ("title", "description", "recovery"):
                    self.assertTrue(catalogue[code][field].strip())
                self.assertNotEqual(catalogue[code]["title"], code)
                # Ambiguous service codes keep their existing runner contract.
                # The viewers contextualize these codes locally; JSX controls
                # verify both the read-only recovery and original diagnostics.
                if code not in {"unauthorized", "invalid_request"}:
                    self.assertNotIn("operator", catalogue[code]["recovery"].lower())
        for code in (
            "github_issue_inspection_unavailable",
            "github_pr_inspection_unavailable",
        ):
            self.assertNotIn("runner", json.dumps(catalogue[code]).lower())
            self.assertNotIn("operator", catalogue[code]["recovery"].lower())
            self.assertIn("repeats only this read", catalogue[code]["recovery"])
        for code in ("issue_write_unknown", "pr_write_unknown"):
            self.assertIn("before authorizing another", catalogue[code]["recovery"])
            self.assertNotIn("operator", catalogue[code]["recovery"].lower())

    def test_shared_runner_codes_preserve_authentication_and_uncertainty_guidance(self):
        catalogue = json.loads(error_catalogue_path().read_text(encoding="utf-8"))
        self.assertIn("runner authentication", catalogue["unauthorized"]["recovery"])
        self.assertIn(
            "until any existing execution is accounted for",
            catalogue["invalid_request"]["recovery"],
        )
