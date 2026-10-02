"""Validate the exported native flow's input pins and serialized component identity."""

import json
from pathlib import Path
import unittest

from laomedo.skill_store import tree_hash


class NativeFlowTests(unittest.TestCase):
    def test_connection_handles_match_serialized_port_schemas(self):
        root = Path(__file__).resolve().parents[1]
        flow = json.loads((root / "examples/native-codex-node/flow.json").read_text())
        nodes = {node["id"]: node for node in flow["data"]["nodes"]}
        for edge in flow["data"]["edges"]:
            source = json.loads(edge["sourceHandle"])
            target = json.loads(edge["targetHandle"])
            output = next(item for item in nodes[edge["source"]]["data"]["node"]["outputs"]
                          if item["name"] == source["name"])
            field = nodes[edge["target"]]["data"]["node"]["template"][target["fieldName"]]
            self.assertEqual(source["output_types"], output["types"])
            self.assertEqual(target["inputTypes"], field.get("input_types", []))
            self.assertEqual(target["type"], field["type"])
            self.assertEqual(source, edge["data"]["sourceHandle"])
            self.assertEqual(target, edge["data"]["targetHandle"])

    def test_native_flow_pins_whole_skill_and_both_output_branches(self):
        root = Path(__file__).resolve().parents[1]
        flow = json.loads((root / "examples/native-codex-node/flow.json").read_text())
        agent = next(n for n in flow["data"]["nodes"]
                     if n["data"]["type"] == "LaomedoCodexAgent")
        fields = agent["data"]["node"]["template"]
        fixture = (root / "examples/skill-agent-pilot/skill/SKILL.md").read_bytes()
        skill = next(n for n in flow["data"]["nodes"] if n["data"]["type"] == "LaomedoSkill")
        self.assertEqual(skill["data"]["node"]["template"]["revision_id"]["value"],
                         tree_hash({"SKILL.md": fixture}))
        self.assertEqual(fields["revision_id"]["value"], "")
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
