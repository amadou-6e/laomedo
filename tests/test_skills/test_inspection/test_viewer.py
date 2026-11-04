"""Protect Skill presentation and installer ownership, not browser acceptance."""

import unittest
from support.paths import repository_root


class SkillViewerBoundaryTests(unittest.TestCase):
    def test_read_failures_share_the_safe_inline_presenter(self):
        root = repository_root()
        overlay = root / "frontend/langflow-skill-viewer"
        for name in ("SkillFilesModal.tsx", "SkillHistory.tsx"):
            text = (overlay / name).read_text(encoding="utf-8")
            self.assertIn("<SkillInspectionError", text)
            self.assertIn("describeInspectionFailure", text)
            self.assertIn("controller.signal.aborted", text)
            self.assertNotIn("Skill files unavailable:", text)
            self.assertNotIn("History unavailable.", text)
            self.assertNotIn("Comparison unavailable.", text)
        inline = (overlay / "SkillInspectionError.tsx").read_text(encoding="utf-8")
        for symbol in ("describeNodeFailure", "<ErrorExplanation", "<CopyIcon"):
            self.assertIn(symbol, inline)
        self.assertNotIn("PopupFrame", inline)
        installer = (root / "tools/apply_langflow_skill_viewer.py").read_text(
            encoding="utf-8"
        )
        for name in (
            "SkillInspectionError.tsx",
            "SkillInspectionError.test.tsx",
            "CanvasQueryState.test.ts",
        ):
            self.assertIn('"' + name + '"', installer)
