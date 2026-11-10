"""Private admission and custody failures need shared user-facing explanations."""

import ast
import json
from pathlib import Path
import unittest


class PrivateAdmissionCatalogueTests(unittest.TestCase):
    def test_private_boundary_codes_have_actionable_catalogue_entries(self):
        root = Path(__file__).resolve().parents[2]
        catalogue = json.loads(
            (root / "frontend/langflow-skill-viewer/node-error-catalog.json").read_text(
                encoding="utf-8"
            )
        )
        owners = (
            root / "src/laomedo/integrations/langflow/authentication",
            root / "src/laomedo/host/credentials/github",
        )
        codes = set()
        for owner in owners:
            for path in owner.glob("*.py"):
                for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                    if (
                        isinstance(node, ast.Constant)
                        and isinstance(node.value, str)
                        and node.value.startswith(
                            ("private_session_", "github_credential_")
                        )
                    ):
                        codes.add(node.value)
        self.assertTrue(codes)
        from laomedo.github.connections.errors import GitHubOAuthError

        codes.add(GitHubOAuthError.code)
        for code in codes:
            with self.subTest(code=code):
                self.assertIn(code, catalogue)
                for field in ("title", "description", "recovery"):
                    self.assertTrue(catalogue[code][field].strip())
