"""Freeze and launch one pinned Langflow 1.12.3 graph in a worker process.

The same in-memory graph whose executable vertices are checked is dispatched.
Posting a flow ID to Langflow's run API would load mutable saved flow state again.
"""

import asyncio
from copy import deepcopy
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version

from laomedo.workflow_run_store import LaunchError, WorkflowRunStore


PINNED_LANGFLOW = "1.12.3"


class FrozenLangflowStage:
    @classmethod
    def from_saved_flow(cls, flow_id, fetch_export):
        """Fetch one saved revision immediately before building its graph."""
        if not isinstance(flow_id, str) or not flow_id or not callable(fetch_export):
            raise LaunchError("unresolved_graph_identity")
        exported = fetch_export(flow_id)
        if not isinstance(exported, dict) or exported.get("id") != flow_id:
            raise LaunchError("saved_flow_identity_mismatch")
        return cls(exported)

    def __init__(self, exported_flow):
        try:
            if version("langflow") != PINNED_LANGFLOW or version("lfx") != PINNED_LANGFLOW:
                raise LaunchError("unsupported_langflow_revision")
        except PackageNotFoundError as exc:
            raise LaunchError("langflow_runtime_unavailable") from exc
        if not isinstance(exported_flow, dict):
            raise LaunchError("unresolved_graph_identity")
        self.export = deepcopy(exported_flow)
        graph_data = self.export.get("data")
        if not isinstance(graph_data, dict) or not isinstance(graph_data.get("nodes"), list) or not graph_data["nodes"]:
            raise LaunchError("unresolved_graph_identity")
        self.component_code = {}
        for node in graph_data["nodes"]:
            if not isinstance(node, dict) or not isinstance(node.get("id"), str) or not node["id"]:
                raise LaunchError("unresolved_graph_identity")
            try:
                code = node["data"]["node"]["template"]["code"]["value"]
            except (KeyError, TypeError):
                raise LaunchError("unresolved_component_identity") from None
            if not isinstance(code, str) or not code.strip() or node["id"] in self.component_code:
                raise LaunchError("unresolved_component_identity")
            self.component_code[node["id"]] = code
        try:
            from lfx.graph.graph.base import Graph
            self.graph = Graph.from_payload(deepcopy(self.export))
            if (set(self.graph.vertex_map) != set(self.component_code) or
                    self.graph.raw_graph_data.get("nodes") != graph_data["nodes"] or
                    self.graph.raw_graph_data.get("edges") != graph_data.get("edges")):
                raise LaunchError("runtime_graph_mismatch")
            for node_id, code in self.component_code.items():
                vertex = self.graph.get_vertex(node_id)
                if (vertex.data["node"]["template"]["code"]["value"] != code or
                        vertex.custom_component is None):
                    raise LaunchError("runtime_component_mismatch")
        except LaunchError:
            raise
        except Exception as exc:
            raise LaunchError("runtime_graph_unresolved") from exc
        self.graph_data = deepcopy(graph_data)
        self._reserved = False
        self.component_revisions = {
            node_id: "sha256:" + sha256(code.encode("utf-8")).hexdigest()
            for node_id, code in self.component_code.items()
        }

    def reserve(self, store: WorkflowRunStore, *, resolved_config, trigger):
        if self._reserved:
            raise LaunchError("stage_already_reserved")
        self._reserved = True
        record = store.reserve(graph=self.graph_data, component_code=self.component_code,
                               resolved_config=resolved_config, trigger=trigger)
        if record["component_revisions"] != self.component_revisions:
            raise LaunchError("recorded_component_mismatch")
        return record

    def execute(self, store: WorkflowRunStore, *, resolved_config, trigger,
                inputs=None, types=None, outputs=None):
        """Execute the checked graph once in a synchronous, isolated worker."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise LaunchError("synchronous_worker_required")
        record = self.reserve(store, resolved_config=resolved_config, trigger=trigger)
        result = store.dispatch(record["run_id"], lambda _run_id: asyncio.run(
            self.graph.arun(inputs=inputs, types=types, outputs=outputs)))
        return store.get(record["run_id"]), result
