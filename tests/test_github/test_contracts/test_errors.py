"""Cover the GitHub public error boundary after interface relocation."""

import ast
import json
import unittest

from support.paths import repository_root
from laomedo.github.issues.contract import ERROR_CODES as ISSUE_CODES
from laomedo.github.pull_requests.contract import ERROR_CODES as PR_CODES


class GitHubErrorCatalogueTests(unittest.TestCase):
    def test_public_contract_and_component_codes_have_descriptive_catalogue_entries(
        self,
    ):
        root = repository_root()
        catalogue = json.loads(
            (
                root / "frontend/langflow-skill-viewer/node-error-catalog.json"
            ).read_text()
        )
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
        for code in ("issue_write_unknown", "pr_write_unknown"):
            self.assertIn("before authorizing another", catalogue[code]["recovery"])
            self.assertNotIn("operator", catalogue[code]["recovery"].lower())
