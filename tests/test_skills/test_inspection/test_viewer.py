"""Protect Skill presentation and installer ownership, not browser acceptance."""

import ast
import unittest
from support.paths import repository_root


class SkillViewerBoundaryTests(unittest.TestCase):
    def test_read_failures_share_the_safe_inline_presenter(self):
        root = repository_root()
        overlay = root / "frontend/langflow-skill-viewer"
        for name in (
            "skills/workspace/SkillFilesModal.tsx",
            "skills/history/SkillHistory.tsx",
        ):
            text = (overlay / name).read_text(encoding="utf-8")
            self.assertIn("<SkillInspectionError", text)
            self.assertIn("describeInspectionFailure", text)
            self.assertIn("controller.signal.aborted", text)
            self.assertNotIn("Skill files unavailable:", text)
            self.assertNotIn("History unavailable.", text)
            self.assertNotIn("Comparison unavailable.", text)
        inline = (overlay / "skills/interface/SkillInspectionError.tsx").read_text(
            encoding="utf-8"
        )
        for symbol in ("describeNodeFailure", "<ErrorExplanation", "<CopyIcon"):
            self.assertIn(symbol, inline)
        self.assertNotIn("PopupFrame", inline)
        installer = (root / "tools/apply_langflow_skill_viewer.py").read_text(
            encoding="utf-8"
        )
        for name in ("skills/interface/CanvasQueryState.test.ts",):
            self.assertIn('"' + name + '"', installer)
        package_source = ast.dump(ast.parse('overlay / "skills"', mode="eval").body)
        self.assertTrue(
            any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "copytree"
                and len(node.args) >= 2
                and ast.dump(node.args[0]) == package_source
                and isinstance(node.args[1], ast.Name)
                and node.args[1].id == "target"
                for node in ast.walk(ast.parse(installer))
            ),
            "Installer must copy the whole concern-owned Skill package",
        )
        for name in (
            "interface/SkillInspectionError.tsx",
            "interface/SkillInspectionError.test.tsx",
            "workspace/SkillFilesModal.test.tsx",
            "editor/SkillSourceEditor.tsx",
        ):
            self.assertTrue((overlay / "skills" / name).is_file(), name)

    def test_skill_packages_have_local_imports_models_and_documented_owners(self):
        import re

        overlay = repository_root() / "frontend/langflow-skill-viewer"
        skills = overlay / "skills"
        for concern in (
            "workspace",
            "editor",
            "explorer",
            "history",
            "search",
            "interface",
            "node",
        ):
            self.assertTrue((skills / concern / "README.md").is_file(), concern)
        self.assertFalse(list(overlay.glob("Skill*.tsx")))
        paths = [*skills.rglob("*.ts"), *skills.rglob("*.tsx")]
        self.assertTrue(paths)
        for path in paths:
            source = path.read_text(encoding="utf-8")
            for specifier in re.findall(r"""["'](\.[^"']+)["']""", source):
                if path.relative_to(
                    skills
                ).as_posix() == "node/SkillNodeControls.test.tsx" and specifier in {
                    "./index",
                    "./utils",
                    "../NodeInputField",
                }:
                    # This test is deployed beside upstream input rendering;
                    # its index is the actual RenderAgentInputParameters adapter.
                    continue
                # Local module specifiers have no spaces or interpolation. Other
                # relative strings are working-file paths, not code imports.
                if (
                    " " in specifier
                    or "${" in specifier
                    or not re.search(
                        r"(?:from\s+|import\(|mock\()"
                        + re.escape('"' + specifier + '"'),
                        source,
                    )
                ):
                    continue
                target = path.parent / specifier
                self.assertTrue(
                    any(
                        target.with_suffix(suffix).is_file()
                        for suffix in (".ts", ".tsx")
                    ),
                    (path, specifier),
                )
        modal = (skills / "workspace/SkillFilesModal.tsx").read_text(encoding="utf-8")
        self.assertNotIn('from "monaco-editor', modal)
        models = (skills / "models.ts").read_text(encoding="utf-8")
        for name in ("Commit", "History", "SkillFile", "Snapshot"):
            self.assertIn("export type " + name + " =", models)
