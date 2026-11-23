"""Nested assistant overlay modules resolve at the installed source boundary."""

from pathlib import Path
import re
import unittest

from support.paths import repository_root


class AssistantFrontendModulesTests(unittest.TestCase):
    def test_relative_imports_resolve_to_owned_modules_or_assets(self):
        root = repository_root() / "frontend/langflow-skill-viewer/assistant"
        for path in root.rglob("*"):
            if path.suffix not in {".ts", ".tsx"}:
                continue
            for reference in re.findall(
                r"(?:from\s+|import\s+|(?:mock|requireActual)\()['\"](\.[^'\"]+)['\"]",
                path.read_text(encoding="utf-8"),
            ):
                target = path.parent / reference
                with self.subTest(module=path.relative_to(root), reference=reference):
                    self.assertTrue(target.resolve().is_relative_to(root.resolve()))
                    self.assertTrue(
                        target.is_file()
                        or any(
                            Path(str(target) + extension).is_file()
                            for extension in (".ts", ".tsx")
                        )
                    )

    def test_installer_entrypoints_resolve_without_forwarding_modules(self):
        root = repository_root()
        installer = (root / "tools/apply_langflow_assistant.py").read_text(
            encoding="utf-8"
        )
        imports = re.findall(r"laomedoAssistant/([^\"]+)", installer)
        self.assertTrue(imports)
        for reference in imports:
            with self.subTest(reference=reference):
                self.assertTrue(
                    (
                        root
                        / "frontend/langflow-skill-viewer/assistant"
                        / (reference + ".tsx")
                    ).is_file()
                    or (
                        root
                        / "frontend/langflow-skill-viewer/assistant"
                        / (reference + ".ts")
                    ).is_file()
                )
