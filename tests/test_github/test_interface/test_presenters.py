"""Guard GitHub inspection failures and complete feature deployment."""

import ast
import json
import re
import unittest

from support.paths import repository_root


class GitHubInspectionPresenterTests(unittest.TestCase):
    def test_changed_read_producers_have_descriptive_catalogue_entries(self):
        overlay = repository_root() / "frontend/langflow-skill-viewer"
        catalogue = json.loads(
            (overlay / "node-error-catalog.json").read_text(encoding="utf-8")
        )
        for relative in (
            "github/interface/InspectionError.tsx",
            "github/issues/IssueViewerModal.tsx",
            "github/pull_requests/PRViewerModal.tsx",
        ):
            source = (overlay / relative).read_text(encoding="utf-8")
            codes = set(re.findall(r"\"([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\"", source))
            self.assertTrue(codes, relative)
            self.assertFalse(
                codes - catalogue.keys(), (relative, codes - catalogue.keys())
            )
            for code in codes:
                for field in ("title", "description", "recovery"):
                    self.assertTrue(catalogue[code][field].strip(), (code, field))

    def test_installer_deploys_the_complete_github_feature(self):
        source = (repository_root() / "tools/apply_langflow_skill_viewer.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        owner = ast.dump(ast.parse('overlay / "github"', mode="eval").body)
        self.assertTrue(
            any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "copytree"
                and node.args
                and ast.dump(node.args[0]) == owner
                for node in ast.walk(tree)
            )
        )
        for name in ("ErrorExplanation.tsx", "CopyIcon.tsx", "nodeErrors.ts"):
            self.assertIn('"' + name + '"', source)

    def test_patch_context_uses_the_defining_github_viewer_paths(self):
        overlay = repository_root() / "frontend/langflow-skill-viewer"
        for patch in overlay.rglob("*.patch"):
            source = patch.read_text(encoding="utf-8")
            self.assertNotIn("@/modals/issueViewerModal", source, patch)
            self.assertNotIn("@/modals/prViewerModal", source, patch)
        agent_patch = (overlay / "agents.patch").read_text(encoding="utf-8")
        for owner in ("issues", "pull_requests"):
            self.assertIn("@/modals/github/" + owner, agent_patch)
