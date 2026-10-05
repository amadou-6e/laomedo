"""Credential-free checks of the pinned Langflow launch graph boundary."""

from copy import deepcopy
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import time
import unittest
from unittest.mock import patch

from laomedo.langflow_stage_adapter import FrozenLangflowStage
from laomedo.work_graph.github import import_pages
from laomedo.work_graph.launch import launch_github_saved_flow_stage, launch_work_stage
from laomedo.workflow_run_store import LaunchError, WorkflowRunStore


FLOW = Path(__file__).resolve().parents[1] / "experiments" / "exp03" / "flow.json"


def pinned_runtime_available():
    try:
        return version("langflow") == "1.12.3" and version("lfx") == "1.12.3"
    except PackageNotFoundError:
        return False


def field(flow, node_id, name):
    return next(node for node in flow["data"]["nodes"] if node["id"] == node_id)[
        "data"]["node"]["template"][name]


@unittest.skipUnless(pinned_runtime_available(),
                     "requires the optional pinned Langflow 1.12.3 runtime")
class LangflowStageAdapterTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = WorkflowRunStore(self.root / "runs.sqlite3")
        self.flow = json.loads(FLOW.read_text(encoding="utf-8"))
        self.gate = self.root / "release"
        field(self.flow, "Exp03Pause-exp03", "gate")["value"] = str(self.gate)

    def execute(self, stage):
        return stage.execute(self.store, resolved_config={"mode": "no-model"},
                             trigger={"type": "fixture"},
                             inputs=[{"input_value": "TASK"}], types=["chat"],
                             outputs=["ChatOutput-exp03"])

    def test_missing_or_unbuildable_revision_refuses_before_reservation(self):
        with self.assertRaisesRegex(LaunchError, "saved_flow_identity_mismatch"):
            FrozenLangflowStage.from_saved_flow("selected-flow", lambda _id: self.flow)
        missing = deepcopy(self.flow)
        del field(missing, "Exp03Marker-exp03", "code")["value"]
        with self.assertRaisesRegex(LaunchError, "unresolved_component_identity"):
            FrozenLangflowStage(missing)
        invalid = deepcopy(self.flow)
        field(invalid, "Exp03Marker-exp03", "code")["value"] = "this is not Python"
        with self.assertRaisesRegex(LaunchError, "runtime_graph_unresolved"):
            FrozenLangflowStage(invalid)
        from lfx.graph.graph.base import Graph
        original = Graph.from_payload

        def wrong_runtime(payload):
            graph = original(payload)
            graph.get_vertex("Exp03Marker-exp03").data["node"]["template"]["code"]["value"] = "other code"
            return graph

        with patch.object(Graph, "from_payload", side_effect=wrong_runtime):
            with self.assertRaisesRegex(LaunchError, "runtime_component_mismatch"):
                FrozenLangflowStage(self.flow)
        self.assertEqual(self.store.counters(), {"runs": 0,
            "dispatch_attempts": 0, "synthetic_dispatches": 0})

    def test_paused_run_keeps_built_graph_and_new_launch_uses_changed_code(self):
        self.flow["id"] = "selected-flow"
        fetched = []

        def fetch(flow_id):
            fetched.append(flow_id)
            return self.flow

        frozen = FrozenLangflowStage.from_saved_flow("selected-flow", fetch)
        initial_code = frozen.component_revisions["Exp03Marker-exp03"]
        observed = {}

        def run_first():
            try:
                observed["first"] = self.execute(frozen)
            except Exception as exc:
                observed["error"] = exc

        worker = Thread(target=run_first, daemon=True)
        worker.start()
        deadline = time.monotonic() + 20
        while not self.gate.with_suffix(".entered").exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(self.gate.with_suffix(".entered").exists(), observed)
        changed = deepcopy(self.flow)
        field(changed, "Exp03Marker-exp03", "marker")["value"] = "AFTER"
        code = field(changed, "Exp03Marker-exp03", "code")
        code["value"] = code["value"].replace("|{self.marker}", "|V2:{self.marker}")
        self.assertNotEqual(code["value"], field(self.flow, "Exp03Marker-exp03", "code")["value"])
        self.gate.write_text("released", encoding="utf-8")
        worker.join(20)
        self.assertFalse(worker.is_alive())
        self.assertNotIn("error", observed)
        first_record, first_result = observed["first"]
        self.assertIn("TASK|BEFORE", str(first_result))
        self.assertEqual(first_record["component_revisions"]["Exp03Marker-exp03"], initial_code)
        with self.assertRaisesRegex(LaunchError, "stage_already_reserved"):
            self.execute(frozen)
        self.flow = changed
        second_record, second_result = self.execute(
            FrozenLangflowStage.from_saved_flow("selected-flow", fetch))
        self.assertIn("TASK|V2:AFTER", str(second_result))
        self.assertNotEqual(second_record["component_revisions"]["Exp03Marker-exp03"], initial_code)
        self.assertNotEqual(second_record["graph_revision"], first_record["graph_revision"])
        self.assertEqual(fetched, ["selected-flow", "selected-flow"])
        self.assertEqual(self.store.counters()["dispatch_attempts"], 2)

    def test_work_graph_gate_launches_the_checked_langflow_graph(self):
        corpus = json.loads((FLOW.parents[0] / ".." / "exp16" / "corpus.json")
                            .resolve().read_text(encoding="utf-8"))
        frozen = import_pages("verify/exp16", corpus["base"],
                              fetched_at="2026-10-05T10:00:00+00:00")
        current = import_pages("verify/exp16", corpus["content_changed"],
                               fetched_at="2026-10-05T10:01:00+00:00")
        self.gate.write_text("released", encoding="utf-8")
        stage = FrozenLangflowStage(self.flow)

        def fixture_authority(ref, binding):
            return {"grant_id": ref, "operator_authorized": True,
                "work_key": "github:S-20",
                "graph_snapshot_id": binding["selected_graph_snapshot_id"],
                "runner": "langflow-local", "scope": "stage-launch",
                "expires_at": "2026-10-05T10:10:00+00:00",
                "limits": {"timeout_seconds": 60, "max_turns": 0}}

        from datetime import datetime
        record, result = launch_work_stage(frozen=frozen,
            source_fetch=lambda _repository: current,
            work_key="github:S-20", choice="pinned", stage=stage,
            store=self.store, grant_ref="synthetic", grant_authority=fixture_authority,
            resolved_config={"mode": "no-model"},
            inputs=[{"input_value": "TASK"}], types=["chat"],
            outputs=["ChatOutput-exp03"],
            now=datetime.fromisoformat("2026-10-05T10:00:00+00:00"))
        self.assertIn("TASK|BEFORE", str(result))
        binding = json.loads(record["trigger_json"])
        self.assertEqual(binding["selected_graph_snapshot_id"], frozen.snapshot_id)
        self.assertEqual(binding["authorization_graph_snapshot_id"], current.snapshot_id)
        self.assertEqual(self.store.counters()["dispatch_attempts"], 1)

    def test_saved_flow_entrypoint_routes_through_live_source_and_grant_gate(self):
        corpus = json.loads((FLOW.parents[0] / ".." / "exp16" / "corpus.json")
                            .resolve().read_text(encoding="utf-8"))
        frozen = import_pages("verify/exp16", corpus["base"],
                              fetched_at="2026-10-05T10:00:00+00:00")
        current = import_pages("verify/exp16", corpus["base"],
                               fetched_at="2026-10-05T10:01:00+00:00")
        self.flow["id"] = "selected-flow"
        exports = []

        def fetch_export(flow_id):
            exports.append(flow_id)
            return self.flow

        from datetime import datetime
        arguments = {"frozen": frozen, "work_key": "github:S-20",
            "flow_id": "selected-flow", "fetch_export": fetch_export,
            "store": self.store, "grant_ref": "synthetic",
            "grant_authority": None, "resolved_config": {"mode": "no-model"},
            "inputs": [{"input_value": "TASK"}], "types": ["chat"],
            "outputs": ["ChatOutput-exp03"],
            "now": datetime.fromisoformat("2026-10-05T10:00:00+00:00")}
        with patch("laomedo.work_graph.github.fetch", return_value=current) as fetch:
            with self.assertRaisesRegex(LaunchError, "grant_authority_required"):
                launch_github_saved_flow_stage(**arguments)
            fetch.assert_called_once_with("verify/exp16")
        self.assertEqual(self.store.counters()["runs"], 0)

        def fixture_authority(ref, binding):
            return {"grant_id": ref, "operator_authorized": True,
                "work_key": "github:S-20",
                "graph_snapshot_id": binding["selected_graph_snapshot_id"],
                "runner": "langflow-local", "scope": "stage-launch",
                "expires_at": "2026-10-05T10:10:00+00:00",
                "limits": {"timeout_seconds": 60, "max_turns": 0}}

        self.gate.write_text("released", encoding="utf-8")
        arguments["grant_authority"] = fixture_authority
        with patch("laomedo.work_graph.github.fetch", return_value=current) as fetch:
            record, result = launch_github_saved_flow_stage(**arguments)
            fetch.assert_called_once_with("verify/exp16")
        self.assertIn("TASK|BEFORE", str(result))
        self.assertEqual(exports, ["selected-flow", "selected-flow"])
        self.assertEqual(json.loads(record["trigger_json"])["source_choice"], "unchanged")
        self.assertEqual(self.store.counters()["dispatch_attempts"], 1)


if __name__ == "__main__":
    unittest.main()
