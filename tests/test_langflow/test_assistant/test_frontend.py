"""Nested assistant overlay modules resolve at the installed source boundary."""

from pathlib import Path
import re
from runpy import run_path
import tempfile
import unittest
import inspect
import sys
from unittest.mock import patch

from support.paths import repository_root


class AssistantFrontendModulesTests(unittest.TestCase):
    def test_installer_copies_nested_modules_tests_and_assets(self):
        root = repository_root()
        apply = run_path(str(root / "tools/apply_langflow_assistant.py"))[
            "apply_assistant"
        ]
        with tempfile.TemporaryDirectory() as temporary:
            checkout = Path(temporary)
            frontend = checkout / "src/frontend/src"
            inputs = {
                "routes.tsx": '<Route path="" element={<CustomDashboardWrapperPage />}>\n'
                * 2,
                "components/core/appHeaderComponent/index.tsx": "{false && <ModelProviderCount />}",
                "controllers/API/queries/auth/use-post-logout.ts": "    if (autoLogin) {",
                "pages/FlowPage/index.tsx": "                    </main>\n                  </FlowSearchProvider>",
                "pages/FlowPage/components/flowSidebarComponent/components/sidebarSegmentedNav.tsx": "        ))}\n      </SidebarMenu>",
            }
            for relative, value in inputs.items():
                path = frontend / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(value, encoding="utf-8")
            source = root / "frontend/langflow-skill-viewer"
            from langflow.services.database.models.flow.guards import (
                ensure_flow_update_allowed,
            )

            guard = (
                checkout
                / "src/backend/base/langflow/services/database/models/flow/guards.py"
            )
            guard.parent.mkdir(parents=True)
            guard.write_text(
                Path(inspect.getfile(ensure_flow_update_allowed)).read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            with patch.object(sys, "path", [str(root / "tools"), *sys.path]):
                apply(checkout, source)
            destination = frontend / "components/laomedoAssistant"
            for path in (source / "assistant").rglob("*"):
                if not path.is_file() or path.name == "README.md":
                    continue
                relative = path.relative_to(source / "assistant")
                with self.subTest(relative=relative):
                    self.assertEqual(
                        path.read_bytes(), (destination / relative).read_bytes()
                    )

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
