"""Check that the saved Langflow flow binds the reviewed pilot fixture."""

import json
from pathlib import Path
import unittest

from laomedo.skill_store import tree_hash


class PilotFlowTests(unittest.TestCase):
    def test_saved_flow_pins_fixture_and_contains_no_private_paths(self):
        root = Path(__file__).resolve().parents[1] / "examples/skill-agent-pilot"
        flow = json.loads((root / "pilot-flow.json").read_text())
        self.assertEqual(len(flow["data"]["nodes"]), 3)
        node = next(n for n in flow["data"]["nodes"]
                    if n["data"]["type"] == "LaomedoRunner")
        revision = tree_hash({"SKILL.md": (root / "skill/SKILL.md").read_bytes()})
        self.assertEqual(node["data"]["node"]["template"]["revision_id"]["value"],
                         revision)
        self.assertEqual(node["data"]["node"]["template"]["code"]["value"],
                         (root / "langflow_component.py").read_text())
        serialized = json.dumps(flow)
        self.assertNotIn("auth.json", serialized)
        self.assertNotIn("C:\\Users\\", serialized)
        self.assertNotIn("X-Bridge-Key", serialized)


if __name__ == "__main__":
    unittest.main()
