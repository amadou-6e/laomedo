"""Validate the exported native flow's input pins and serialized component identity."""

import json
from pathlib import Path
import unittest

from laomedo.skills.registry.utils import tree_hash


class NativeFlowTests(unittest.TestCase):
    def test_opencode_example_embeds_current_component(self):
        root = Path(__file__).resolve().parents[1]
        flow = json.loads((root / "examples/opencode-node/flow.json").read_text())
        agents = [
            node
            for node in flow["data"]["nodes"]
            if node["data"]["type"] == "LaomedoOpenCodeAgent"
        ]
        self.assertTrue(agents)
        for agent in agents:
            self.assertEqual(
                agent["data"]["node"]["template"]["code"]["value"],
                (root / "components/laomedo/opencode_agent.py").read_text(),
            )

    def test_current_claude_templates_embed_the_neutral_adapter_and_optional_skills(
        self,
    ):
        root = Path(__file__).resolve().parents[1]
        source = (root / "components/laomedo/claude_agent.py").read_text()
        for relative in (
            "examples/claude-agent/current-template-flow.json",
            "examples/claude-agent/flow.json",
        ):
            flow = json.loads((root / relative).read_text())
            agents = [
                node
                for node in flow["data"]["nodes"]
                if node["data"]["type"] == "LaomedoClaudeAgent"
            ]
            self.assertTrue(agents)
            for agent in agents:
                fields = agent["data"]["node"]["template"]
                self.assertEqual(fields["code"]["value"], source)
                self.assertFalse(fields["skill_reference"]["required"])

    def test_connection_handles_match_serialized_port_schemas(self):
        root = Path(__file__).resolve().parents[1]
        flow = json.loads((root / "examples/native-codex-node/flow.json").read_text())
        nodes = {node["id"]: node for node in flow["data"]["nodes"]}
        for edge in flow["data"]["edges"]:
            source = json.loads(edge["sourceHandle"])
            target = json.loads(edge["targetHandle"])
            output = next(
                item
                for item in nodes[edge["source"]]["data"]["node"]["outputs"]
                if item["name"] == source["name"]
            )
            field = nodes[edge["target"]]["data"]["node"]["template"][
                target["fieldName"]
            ]
            self.assertEqual(source["output_types"], output["types"])
            self.assertEqual(target["inputTypes"], field.get("input_types", []))
            self.assertEqual(target["type"], field["type"])
            self.assertEqual(source, edge["data"]["sourceHandle"])
            self.assertEqual(target, edge["data"]["targetHandle"])

    def test_native_flow_pins_whole_skill_and_both_output_branches(self):
        root = Path(__file__).resolve().parents[1]
        flow = json.loads((root / "examples/native-codex-node/flow.json").read_text())
        agent = next(
            n for n in flow["data"]["nodes"] if n["data"]["type"] == "LaomedoCodexAgent"
        )
        fields = agent["data"]["node"]["template"]
        fixture = (root / "examples/skill-agent-pilot/skill/SKILL.md").read_bytes()
        skill = next(
            n for n in flow["data"]["nodes"] if n["data"]["type"] == "LaomedoSkill"
        )
        self.assertEqual(
            skill["data"]["node"]["template"]["revision_id"]["value"],
            tree_hash({"SKILL.md": fixture}),
        )
        self.assertEqual(fields["revision_id"]["value"], "")
        self.assertTrue(fields["run_reference_json"].get("override_skip"))
        self.assertFalse(fields["run_reference"].get("override_skip", False))
        self.assertEqual(
            fields["code"]["value"],
            (root / "components/laomedo/codex_agent.py").read_text(),
        )
        names = {
            e["data"]["sourceHandle"]["name"]
            for e in flow["data"]["edges"]
            if e["source"] == agent["id"]
        }
        self.assertEqual(names, {"answer", "run"})
        self.assertTrue(
            all(o["group_outputs"] for o in agent["data"]["node"]["outputs"])
        )
        self.assertNotIn("auth.json", json.dumps(flow))
        self.assertNotIn("C:\\Users\\", json.dumps(flow))


if __name__ == "__main__":
    unittest.main()
