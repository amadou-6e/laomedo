"""The profile producer has its own catalogue coverage, independent of Agents."""

import ast
import json
import re
from pathlib import Path
import unittest


class ProfileCatalogueTests(unittest.TestCase):
    def test_every_public_profile_code_has_descriptive_catalogue_coverage(self):
        repo = Path(__file__).resolve().parents[2]
        catalogue = json.loads(
            (
                repo / "frontend/langflow-skill-viewer/node-error-catalog.json"
            ).read_text()
        )
        codes = set()
        for path in (repo / "src/laomedo/integrations/langflow/local_profiles").glob(
            "*.py"
        ):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                if (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and node.value.startswith("profile_")
                    and " " not in node.value
                ):
                    # Model-validator reasons are caught and projected to the safe
                    # profile_input_invalid code rather than emitted publicly.
                    if node.value not in {
                        "profile_name_invalid",
                        "profile_pin_invalid",
                        "profile_pin_mismatch",
                    }:
                        codes.add(node.value)
        for path in (repo / "frontend/langflow-skill-viewer/profiles").glob("*.ts*"):
            codes.update(
                re.findall(
                    r'["\']((?:profile_[a-z_]+)|app_signout_unconfirmed)["\']',
                    path.read_text(encoding="utf-8-sig"),
                )
            )
        self.assertIn("profile_creation_unconfirmed", codes)
        for code in codes:
            with self.subTest(code=code):
                self.assertIn(code, catalogue)
                for field in ("title", "description", "recovery"):
                    self.assertTrue(catalogue[code][field].strip())
