"""Validate the exported native flow's input pins and serialized component identity."""

import json
from pathlib import Path
import unittest

from laomedo.skill_store import tree_hash


class NativeFlowTests(unittest.TestCase):
    def test_native_flow_pins_whole_skill_and_both_output_branches(self):
        root = Path(__file__).resolve().parents[1]
        flow = json.loads((root / "examples/native-codex-node/flow.json").read_text())
        agent = next(n for n in flow["data"]["nodes"]
                     if n["data"]["type"] == "LaomedoCodexAgent")
        fields = agent["data"]["node"]["template"]
        fixture = (root / "examples/skill-agent-pilot/skill/SKILL.md").read_bytes()
        self.assertEqual(fields["revision_id"]["value"], tree_hash({"SKILL.md": fixture}))
        self.assertEqual(fields["code"]["value"],
                         (root / "components/laomedo/codex_agent.py").read_text())
        names = {e["data"]["sourceHandle"]["name"] for e in flow["data"]["edges"]
                 if e["source"] == agent["id"]}
        self.assertEqual(names, {"answer", "run"})
        self.assertTrue(all(o["group_outputs"] for o in agent["data"]["node"]["outputs"]))
        self.assertNotIn("auth.json", json.dumps(flow))
        self.assertNotIn("C:\\Users\\", json.dumps(flow))


if __name__ == "__main__":
    unittest.main()
