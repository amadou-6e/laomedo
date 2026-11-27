"""Request-local MCP dependencies for read/cancel Agent operations."""

from copy import deepcopy
from importlib.metadata import version
import inspect

from laomedo.agents.mcp.errors import McpError
from laomedo.agents.mcp.settings import SUPPORTED_LFX_VERSION


class McpGraphPolicy:
    """Keep control operations independent of MCP discovery without editing flows.

    The app installs one version-checked graph admission adapter. Filtering happens
    before native scheduling or connection-bearing outputs execute.
    Only request-local execution data is changed, never the supplied saved flow.
    """

    _native_initialize = None
    _native_sort = None

    def __init__(self, graph):
        """Keep a reversible execution view on this graph instance only."""
        self.graph = graph
        self.saved = None
        self.parameters = []
        self.cycles = None

    @classmethod
    def install(cls):
        """Install once, refusing an unknown or conflicting scheduling adapter."""
        from lfx.graph.graph.base import Graph

        if (
            Graph.sort_vertices is cls.sort_vertices
            and Graph.initialize is cls.initialize
        ):
            return
        if version("lfx") != SUPPORTED_LFX_VERSION:
            raise McpError("mcp_native_version_unsupported")
        for name, expected in (
            ("initialize", ("self",)),
            ("sort_vertices", ("self", "stop_component_id", "start_component_id")),
        ):
            method = getattr(Graph, name)
            if (
                method.__module__ != "lfx.graph.graph.base"
                or method.__qualname__ != "Graph." + name
                or tuple(inspect.signature(method).parameters) != expected
            ):
                raise McpError("mcp_native_version_unsupported")
        cls._native_initialize = staticmethod(Graph.initialize)
        cls._native_sort = staticmethod(Graph.sort_vertices)
        Graph.initialize = cls.initialize
        Graph.sort_vertices = cls.sort_vertices

    @staticmethod
    def initialize(graph):
        """Restore the full definition before native rebuilds or warm-graph reuse."""
        policy = getattr(graph, "_laomedo_mcp_policy", None)
        if policy is not None:
            policy.restore()
        return McpGraphPolicy._native_initialize(graph)

    @staticmethod
    def sort_vertices(graph, stop_component_id=None, start_component_id=None):
        """Use effective runtime operations, retaining explicitly played nodes."""
        policy = getattr(graph, "_laomedo_mcp_policy", None)
        if policy is None:
            policy = McpGraphPolicy(graph)
            graph._laomedo_mcp_policy = policy
        policy.restore()
        policy.apply({stop_component_id, start_component_id} - {None})
        return McpGraphPolicy._native_sort(graph, stop_component_id, start_component_id)

    def restore(self):
        """Undo only our temporary view, without restoring stale run results."""
        if self.saved is None:
            return
        for name, value in self.saved.items():
            setattr(self.graph, name, value)
        for vertex, parameters, raw_parameters in self.parameters:
            vertex.params = {**vertex.params, "mcp_tools": parameters["mcp_tools"]}
            vertex.raw_params = {
                **vertex.raw_params,
                "mcp_tools": raw_parameters["mcp_tools"],
            }
        self.graph.run_manager.cycle_vertices = self.cycles
        self.saved = None
        self.parameters = []

    def apply(self, explicit):
        """Prune scheduling and recursive input resolution together for this run."""
        from lfx.graph.graph.utils import find_cycle_vertices

        graph = self.graph
        nodes = [
            {
                "id": v.id,
                "data": {
                    "type": v.data.get("type"),
                    "node": {
                        "template": {"operation": {"value": v.params.get("operation")}}
                    },
                },
            }
            for v in graph.vertices
        ]
        edges = [
            {
                "source": e.source_id,
                "target": e.target_id,
                "data": {"targetHandle": {"fieldName": e.target_param}},
            }
            for e in graph.edges
        ]
        filtered_nodes, filtered_edges = self.execution_graph(nodes, edges, explicit)
        if filtered_edges is edges:
            return
        kept = {node["id"] for node in filtered_nodes}
        edge_keys = {
            (e["source"], e["target"], e["data"]["targetHandle"]["fieldName"])
            for e in filtered_edges
        }
        self.saved = {
            name: getattr(graph, name)
            for name in (
                "vertices",
                "vertex_map",
                "edges",
                "top_level_vertices",
                "_cycle_vertices",
                "_is_cyclic",
                "_is_state_vertices",
                "_is_input_vertices",
                "_is_output_vertices",
                "has_session_id_vertices",
                "predecessor_map",
                "successor_map",
                "in_degree_map",
                "parent_child_map",
            )
        }
        self.cycles = graph.run_manager.cycle_vertices
        graph.vertices = [v for v in graph.vertices if v.id in kept]
        graph.vertex_map = {v.id: v for v in graph.vertices}
        graph.edges = [
            e
            for e in graph.edges
            if (e.source_id, e.target_id, e.target_param) in edge_keys
        ]
        graph._cycle_vertices = set(
            find_cycle_vertices([(e.source_id, e.target_id) for e in graph.edges])
        )
        graph._is_cyclic = bool(graph._cycle_vertices)
        graph.run_manager.cycle_vertices = graph.cycle_vertices.copy()
        for name in (
            "top_level_vertices",
            "_is_input_vertices",
            "_is_output_vertices",
            "has_session_id_vertices",
            "_is_state_vertices",
        ):
            values = getattr(graph, name)
            if values is not None:
                setattr(graph, name, [v for v in values if v in kept])
        removed_targets = {
            e["target"]
            for e in edges
            if (e["source"], e["target"], e["data"]["targetHandle"]["fieldName"])
            not in edge_keys
            and e["data"]["targetHandle"]["fieldName"] == "mcp_tools"
        }
        for vertex in graph.vertices:
            if vertex.id in removed_targets:
                self.parameters.append((vertex, vertex.params, vertex.raw_params))
                vertex.params = {**vertex.params, "mcp_tools": []}
                vertex.raw_params = {**vertex.raw_params, "mcp_tools": []}
        graph.build_graph_maps()

    @staticmethod
    def execution_graph(nodes, edges, explicit=frozenset()):
        """Remove control-only dependencies; retain every shared active consumer.

        Walk backwards from the removed edges, then retain ancestors needed by
        any remaining consumer. This also preserves cycles with active exits.
        Unrelated orphan nodes are outside this policy.
        """
        inactive = {
            node["id"]
            for node in nodes
            if node.get("data", {}).get("type")
            in {"LaomedoCodexAgent", "LaomedoClaudeAgent", "LaomedoOpenCodeAgent"}
            and node.get("data", {})
            .get("node", {})
            .get("template", {})
            .get("operation", {})
            .get("value")
            in {"status", "cancel"}
        }
        removed = [
            edge
            for edge in edges
            if edge.get("target") in inactive
            and edge.get("data", {}).get("targetHandle", {}).get("fieldName")
            == "mcp_tools"
        ]
        if not removed:
            return nodes, edges
        remaining = [edge for edge in edges if edge not in removed]
        ancestors = {edge["source"] for edge in removed}
        while True:
            expanded = ancestors | {
                edge["source"] for edge in remaining if edge["target"] in ancestors
            }
            if expanded == ancestors:
                break
            ancestors = expanded
        retained = (ancestors & (inactive | set(explicit))) | {
            edge["source"]
            for edge in remaining
            if edge["source"] in ancestors and edge["target"] not in ancestors
        }
        while True:
            expanded = retained | {
                edge["source"] for edge in remaining if edge["target"] in retained
            }
            if expanded == retained:
                break
            retained = expanded
        discarded = ancestors - retained
        # Copy only the changed execution view; callers still own the saved data.
        return (
            deepcopy([node for node in nodes if node["id"] not in discarded]),
            deepcopy(
                [
                    edge
                    for edge in remaining
                    if edge["source"] not in discarded
                    and edge["target"] not in discarded
                ]
            ),
        )
