"""Explicit patches over saved graph bytes, preserving unmentioned private settings."""

from copy import deepcopy
import json
from uuid import uuid4

from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.models import (
    DraftGraph,
    DraftNode,
    DraftEdge,
)


class GraphEditor:
    """Validate patch values/ports through installed metadata without executing components."""

    def __init__(self, catalog):
        """Use the same policy-filtered installed catalog as existing authoring tools."""
        self.catalog = catalog

    def identity(self, node):
        """Resolve a saved node through the safe canonical projection, never model code."""
        projected = self.catalog.project({"nodes": [node]})["nodes"]
        if not projected or projected[0].get("unsupported"):
            raise AssistantError("assistant_component_metadata_unavailable", 422)
        return projected[0]["component_type"]

    def edge_identity(self, edge):
        """Read exact named handles without guessing from labels or string fragments."""
        handles = edge.get("data", {})
        return (
            edge.get("source"),
            handles.get("sourceHandle", {}).get("name"),
            edge.get("target"),
            handles.get("targetHandle", {}).get("fieldName"),
        )

    def connection(self, definition, nodes):
        """Reuse canonical compiler port checks, then bind handles to actual saved IDs."""
        source, target = nodes.get(definition.source), nodes.get(definition.target)
        if source is None or target is None:
            raise AssistantError("assistant_edge_node_unknown", 422)
        compiled, _ = self.catalog.compile(
            DraftGraph(
                nodes=[
                    DraftNode(key="from", component_type=self.identity(source)),
                    DraftNode(key="to", component_type=self.identity(target)),
                ],
                edges=[
                    DraftEdge(
                        source="from",
                        output=definition.output,
                        target="to",
                        input=definition.input,
                    )
                ],
                allow_incomplete=True,
            )
        )
        edge = compiled["edges"][0]
        outgoing, incoming = edge["data"]["sourceHandle"], edge["data"]["targetHandle"]
        outputs = source.get("data", {}).get("node", {}).get("outputs", [])
        saved_output = next(
            (item for item in outputs if item.get("name") == definition.output), None
        )
        field = (
            target.get("data", {})
            .get("node", {})
            .get("template", {})
            .get(definition.input)
        )
        if (
            saved_output is None
            or not isinstance(field, dict)
            or saved_output.get("types", []) != outgoing["output_types"]
            or field.get("input_types", []) != incoming["inputTypes"]
            or field.get("type") != incoming["type"]
        ):
            raise AssistantError("assistant_port_incompatible", 422)
        outgoing["id"], incoming["id"] = definition.source, definition.target
        edge.update(
            id="assistant-edge-" + uuid4().hex,
            source=definition.source,
            target=definition.target,
            sourceHandle=json.dumps(outgoing),
            targetHandle=json.dumps(incoming),
        )
        return edge, bool(field.get("list"))

    def apply(self, data, changes):
        """Return a private deep copy plus safe preview; never rebuild untouched nodes."""
        result = deepcopy(data or {})
        result.setdefault("nodes", [])
        result.setdefault("edges", [])
        nodes = {node["id"]: node for node in result["nodes"]}
        if len(nodes) != len(result["nodes"]) or len(nodes) > 100:
            raise AssistantError("assistant_graph_too_large", 422)
        preview = []
        if changes.name is not None:
            preview.append("Rename graph to " + changes.name)
        seen = set()
        for update in changes.updates:
            if update.node_id not in nodes or update.node_id in seen:
                raise AssistantError("assistant_duplicate_node", 422)
            seen.add(update.node_id)
            node = nodes[update.node_id]
            preview.extend(
                self.catalog.update_saved_fields(
                    node, self.identity(node), update.fields
                )
            )
        for identifier in changes.remove_nodes:
            if identifier not in nodes or identifier in seen:
                raise AssistantError("assistant_duplicate_node", 422)
            seen.add(identifier)
            edges = result["edges"]
            retained = [
                edge
                for edge in edges
                if identifier not in (edge.get("source"), edge.get("target"))
            ]
            preview.append(
                f"Remove node {identifier} and {len(edges) - len(retained)} incident connections"
            )
            result["edges"] = retained
            result["nodes"].remove(nodes.pop(identifier))
        for definition in changes.add_nodes:
            compiled, diagnostics = self.catalog.compile(
                DraftGraph(nodes=[definition], allow_incomplete=True)
            )
            node = compiled["nodes"][0]
            if node["id"] in nodes:
                raise AssistantError("assistant_duplicate_node", 422)
            node["position"] = {
                "x": (len(nodes) % 3) * 420,
                "y": (len(nodes) // 3) * 400,
            }
            result["nodes"].append(node)
            nodes[node["id"]] = node
            preview.append("Add " + definition.component_type + " as " + node["id"])
            preview.extend("Incomplete: " + value for value in diagnostics)
        for definition in changes.disconnect:
            identity = (
                definition.source,
                definition.output,
                definition.target,
                definition.input,
            )
            found = [
                edge for edge in result["edges"] if self.edge_identity(edge) == identity
            ]
            if len(found) != 1:
                raise AssistantError("assistant_port_unknown", 422)
            result["edges"].remove(found[0])
            preview.append("Disconnect " + " / ".join(identity))
        for definition in changes.connect:
            edge, multiple = self.connection(definition, nodes)
            identity = self.edge_identity(edge)
            if any(
                self.edge_identity(old) == identity
                or (not multiple and self.edge_identity(old)[2:] == identity[2:])
                for old in result["edges"]
            ):
                raise AssistantError("assistant_edge_conflict", 422)
            result["edges"].append(edge)
            preview.append("Connect " + " / ".join(identity))
        if (
            not result["nodes"]
            or len(result["nodes"]) > 100
            or len(result["edges"]) > 200
        ):
            raise AssistantError("assistant_graph_too_large", 422)
        return result, preview
