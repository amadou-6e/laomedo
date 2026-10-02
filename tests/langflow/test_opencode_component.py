"""Run in pinned Langflow with components/ prepended to PYTHONPATH."""

import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "components"))
from laomedo.opencode_agent import LaomedoOpenCodeAgent
from lfx.custom.custom_component.component import Component
from lfx.custom.utils import build_custom_component_template


class OpenCodeComponentTests(unittest.IsolatedAsyncioTestCase):
    def node(self, **changes):
        node = LaomedoOpenCodeAgent()
        for key, value in {"operation": "fresh", "task": "Read fixture", "model": "test/model",
            "effort": "default", "runner_url": "http://localhost:8767", "timeout_seconds": 210,
            "skill_reference": [{"skill_id": "sample", "revision_id": "sha256:" + "a" * 64,
                                  "tree_hash": "sha256:" + "a" * 64}],
            "skill_id": "", "revision_id": "", "run_reference": None, **changes}.items():
            setattr(node, key, value)
        node._pre_run_setup()
        return node

    async def test_both_outputs_share_one_dispatch(self):
        node = self.node()
        value = {"provider": "opencode", "run_id": "fixture", "status": "completed", "answer": "answer"}
        with patch.object(LaomedoOpenCodeAgent, "_http", return_value=value) as dispatch:
            outputs = await asyncio.gather(node.answer_output(), node.run_output())
        self.assertEqual(dispatch.call_count, 1)
        self.assertEqual(outputs[0].text, "answer")

    async def test_unsupported_variant_and_foreign_resume_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported_opencode_effort"):
            self.node(effort="high")._prepare()
        with self.assertRaisesRegex(ValueError, "run_provider_mismatch"):
            self.node(operation="resume", run_reference={"provider": "codex"})._prepare()

    async def test_template_ports_and_multiple_skills(self):
        code = (ROOT / "components/laomedo/opencode_agent.py").read_text()
        template, _ = build_custom_component_template(Component(_code=code))
        self.assertTrue(template["template"]["skill_reference"]["list"])
        self.assertEqual([item["types"] for item in template["outputs"]], [["Message"], ["JSON"]])
        refs = self.node().skill_reference
        refs.append({**refs[0], "skill_id": "second"})
        self.assertEqual(len(self.node(skill_reference=refs)._prepare()[1]["skill_refs"]), 2)


if __name__ == "__main__":
    unittest.main()
