"""Internal serialization controls, never real-provider acceptance."""

import importlib.util
import json
from hashlib import sha256
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from support.paths import repository_root


@unittest.skipUnless(
    importlib.util.find_spec("lfx"), "Requires the declared Langflow runtime"
)
class GraphBuilderTests(unittest.TestCase):
    def test_cli_bootstraps_runtime_in_a_fresh_interpreter(self):
        root = repository_root()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "graph.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(root / "examples/agents/build_flow.py"),
                    "--provider",
                    "codex",
                    "--model",
                    "internal-structure-check",
                    "--effort",
                    "default",
                    "--runner-url",
                    "http://127.0.0.1:8765",
                    "--task",
                    "Internal construction only; never execute.",
                    "--output",
                    str(target),
                ],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=90,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            flow = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(len(flow["data"]["nodes"]), 1)
            self.assertEqual(
                flow["data"]["nodes"][0]["data"]["type"], "LaomedoCodexAgent"
            )
            self.assertEqual(flow["data"]["edges"], [])

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "maintained_agent_graph",
            repository_root() / "examples/agents/build_flow.py",
        )
        cls.builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.builder)

    def build(self, provider, **kwargs):
        return self.builder.build(
            provider=provider,
            model="internal-structure-check",
            effort="default",
            runner_url="http://127.0.0.1:8765",
            task="Internal construction check; never execute.",
            **kwargs,
        )

    def test_provider_source_optional_skill_and_resume_ports(self):
        for provider in ("codex", "claude", "opencode"):
            for workflow in ("fresh", "resume"):
                with self.subTest(provider=provider, workflow=workflow):
                    flow = self.build(
                        provider, workflow=workflow, follow_up="Follow-up"
                    )
                    nodes = flow["data"]["nodes"]
                    self.assertEqual(len(nodes), 1 if workflow == "fresh" else 2)
                    source = (
                        repository_root()
                        / "components/laomedo"
                        / (provider + "_agent.py")
                    ).read_text(encoding="utf-8")
                    for node in nodes:
                        fields = node["data"]["node"]["template"]
                        self.assertEqual(fields["code"]["value"], source)
                        self.assertEqual(
                            node["data"]["node"]["metadata"]["code_hash"],
                            sha256(source.encode()).hexdigest()[:12],
                        )
                        self.assertFalse(fields["skill_reference"]["required"])
                        # Upstream drops connections to show=False inputs when
                        # loading or refreshing templates. Canvas policy hides
                        # this compatibility input unless actually connected.
                        self.assertTrue(fields["run_reference"]["show"])
                    if workflow == "resume":
                        edge = flow["data"]["edges"][0]
                        self.assertEqual(
                            json.loads(edge["sourceHandle"])["name"], "run"
                        )
                        self.assertEqual(
                            json.loads(edge["targetHandle"])["fieldName"],
                            "run_reference",
                        )

    def test_handoff_never_silently_drops_provenance(self):
        for provider in ("codex", "opencode"):
            flow = self.build(provider, workflow="handoff", follow_up="Selected task")
            self.assertEqual(len(flow["data"]["nodes"]), 3)
            self.assertTrue(
                any(
                    edge["data"]["targetHandle"]["fieldName"] == "handoff_reference"
                    for edge in flow["data"]["edges"]
                )
            )
            handoff = next(
                node for node in flow["data"]["nodes"] if node["id"] == "handoff"
            )
            self.assertEqual(
                handoff["data"]["node"]["template"]["task"]["value"], "Selected task"
            )
        with self.assertRaisesRegex(
            ValueError, "does not expose a provenance handoff input"
        ):
            self.build("claude", workflow="handoff")

    def test_skill_pin_is_explicit_and_resume_requires_follow_up(self):
        pin = {"skill_id": "internal-pin", "revision_id": "sha256:" + "a" * 64}
        flow = self.build("codex", reference=pin)
        self.assertEqual(len(flow["data"]["nodes"]), 2)
        self.assertEqual(
            flow["data"]["edges"][0]["data"]["targetHandle"]["fieldName"],
            "skill_reference",
        )
        skill = next(node for node in flow["data"]["nodes"] if node["id"] == "skill")
        self.assertEqual(
            skill["data"]["node"]["template"]["revision_id"]["value"],
            pin["revision_id"],
        )
        with self.assertRaisesRegex(ValueError, "explicit follow-up"):
            self.build("codex", workflow="resume")
