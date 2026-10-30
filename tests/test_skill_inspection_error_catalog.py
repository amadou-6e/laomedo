"""Internal producer/presentation coverage, not installed browser acceptance."""

import ast
import json
from pathlib import Path
import unittest


class SkillInspectionErrorCatalogueTests(unittest.TestCase):
    """Prevent the previously inventoried viewer gaps from silently returning."""

    def test_affected_producer_codes_have_descriptive_catalogue_entries(self):
        """Read actual literal producers rather than just a new expected list."""
        root = Path(__file__).resolve().parents[1]
        catalogue = json.loads(
            (root / "frontend/langflow-skill-viewer/node-error-catalog.json").read_text(
                encoding="utf-8"
            )
        )
        codes = set()
        for relative in (
            "skills/inspection/utils.py",
            "skills/operations/models.py",
            "skills/authoring/summary.py",
        ):
            tree = ast.parse(
                (root / "src/laomedo" / relative).read_text(encoding="utf-8")
            )
            codes.update(
                node.exc.args[0].value
                for node in ast.walk(tree)
                if isinstance(node, ast.Raise)
                and isinstance(node.exc, ast.Call)
                and node.exc.args
                and isinstance(node.exc.args[0], ast.Constant)
                and isinstance(node.exc.args[0].value, str)
            )
        self.assertTrue(
            {
                "immutable_skill_revision_required",
                "skill_revision_unavailable",
                "skill_revision_unsafe",
                "skill_revision_too_large",
                "skill_operation_invalid",
                "skill_summary_source_unavailable",
            }
            <= codes
        )
        self.assertFalse(codes - catalogue.keys())
        for code in codes | {
            "skill_inspection_unavailable",
            "skill_history_unavailable",
            "skill_comparison_unavailable",
        }:
            with self.subTest(code=code):
                entry = catalogue[code]
                self.assertEqual(set(entry), {"title", "description", "recovery"})
                self.assertTrue(
                    all(
                        type(value) is str and value.strip() for value in entry.values()
                    )
                )
                self.assertNotRegex(
                    " ".join(entry.values()).lower(), r"\boperator\b|\brestart\b"
                )

    def test_inline_viewers_share_presenter_and_installer_owns_new_files(self):
        """Guard actual presentation/packaging boundaries without claiming UI use."""
        root = Path(__file__).resolve().parents[1]
        overlay = root / "frontend/langflow-skill-viewer"
        for name in ("SkillFilesModal.tsx", "SkillHistory.tsx"):
            text = (overlay / name).read_text(encoding="utf-8")
            self.assertIn("<SkillInspectionError", text)
            self.assertIn("describeInspectionFailure", text)
            self.assertNotIn(">Retry<", text)
            self.assertNotIn("<ErrorPopup", text)
            self.assertIn("controller.signal.aborted", text)
        inline = (overlay / "SkillInspectionError.tsx").read_text(encoding="utf-8")
        self.assertIn("describeNodeFailure", inline)
        self.assertIn("<ErrorExplanation", inline)
        self.assertIn("<CopyIcon", inline)
        self.assertNotIn("PopupFrame", inline)
        popup = (overlay / "ErrorPopup.tsx").read_text(encoding="utf-8")
        self.assertIn("<ErrorExplanation", popup)
        self.assertIn("formatErrorCopy(failure)", popup)
        installer = (root / "tools/apply_langflow_skill_viewer.py").read_text(
            encoding="utf-8"
        )
        for name in (
            "SkillInspectionError.tsx",
            "SkillInspectionError.test.tsx",
            "SkillFilesModal.test.tsx",
            "ErrorExplanation.tsx",
        ):
            self.assertIn('"' + name + '"', installer)


if __name__ == "__main__":
    unittest.main()
