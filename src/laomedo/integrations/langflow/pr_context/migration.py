"""Migrate compatible saved PR connections without dropping ambiguous edges."""

from copy import deepcopy
from hashlib import sha256
import json
import re


def _kind(node):
    """Read a node's stable component kind, including extension-qualified names."""
    kind = node.get("data", {}).get("type", "")
    return re.sub(r"^ext:[^:]+:([^@]+)@.+$", r"\1", kind)


def _handle(edge, side):
    """Decode the existing native handle or refuse malformed graph metadata."""
    try:
        value = edge.get("data", {}).get(side + "Handle")
        return deepcopy(
            value if isinstance(value, dict) else json.loads(edge[side + "Handle"])
        )
    except (KeyError, TypeError, ValueError):
        raise ValueError("pr_context_migration_required") from None


def migrate_pr_graph(flow, definition):
    """Return a migrated copy using current trusted PR component metadata.

    Both legacy input edges, incompatible old Task/flat-PR consumers, inline
    values mixed with edges, and edited component code require manual repair.
    The original graph stays unchanged even on refusal. No graph is executed,
    no credential is read and no request is authorized by this transformation.
    """
    result = deepcopy(flow)
    graph = result.get("data", result)
    nodes = {node["id"]: node for node in graph["nodes"]}
    prs = {key for key, node in nodes.items() if _kind(node) == "LaomedoGitHubPR"}
    legacy = {
        key for key in prs if "pr_context" not in nodes[key]["data"]["node"]["template"]
    }
    agents = {"LaomedoCodexAgent", "LaomedoClaudeAgent", "LaomedoOpenCodeAgent"}
    for key in prs:
        node = nodes[key]["data"]["node"]
        if node.get("edited"):
            raise ValueError("pr_context_migration_required")
        template = node["template"]
        incoming = [edge for edge in graph["edges"] if edge["target"] == key]
        if len(incoming) > 1:
            raise ValueError("pr_context_migration_required")
        values = {
            name: template.get(name, {}).get("value")
            for name in ("pr_reference", "operation")
        }
        if incoming and any(values.values()):
            raise ValueError("pr_context_migration_required")
        context = template.get("pr_context", {}).get("value")
        if not incoming and any(values.values()):
            context = {}
            if values["pr_reference"]:
                context["pr"] = values["pr_reference"]
            if values["operation"]:
                operation = values["operation"]
                if isinstance(operation, str):
                    try:
                        operation = json.loads(operation)
                    except ValueError:
                        raise ValueError("pr_context_migration_required") from None
                context["operation"] = operation
        fresh = deepcopy(definition["template"])
        for name, field in template.items():
            if name not in {"code", "pr_context", "pr_reference", "operation"}:
                if name in fresh and isinstance(field, dict):
                    for attr in ("value", "options"):
                        if attr in field:
                            fresh[name][attr] = deepcopy(field[attr])
                elif name not in fresh:
                    fresh[name] = deepcopy(field)
        fresh["pr_context"]["value"] = context
        node["template"] = fresh
        node["outputs"] = deepcopy(definition["outputs"])
        node["field_order"] = deepcopy(definition.get("field_order", []))
        if "code_hash" in node.get("metadata", {}):
            node["metadata"]["code_hash"] = sha256(
                fresh["code"]["value"].encode()
            ).hexdigest()[:12]
    for edge in graph["edges"]:
        source, target = _handle(edge, "source"), _handle(edge, "target")
        name = source.get("name")
        field = target.get("fieldName", target.get("name"))
        if edge["source"] in prs:
            if name == "task":
                if _kind(nodes[edge["target"]]) not in agents or field != "task":
                    raise ValueError("pr_context_migration_required")
            elif name == "pr" and edge["source"] in legacy:
                if not (
                    edge["target"] in prs and field in {"pr_reference", "pr_context"}
                ):
                    raise ValueError("pr_context_migration_required")
            elif name not in {"pr", "operation_result"}:
                raise ValueError("pr_context_migration_required")
            source.update(name="pr", output_types=["Data"])
            if field == "task" and _kind(nodes[edge["target"]]) in agents:
                target["inputTypes"] = ["Message", "Data"]
                nodes[edge["target"]]["data"]["node"]["template"]["task"][
                    "input_types"
                ] = ["Message", "Data"]
        if edge["target"] in prs:
            if field == "pr_reference" and edge["source"] not in prs:
                raise ValueError("pr_context_migration_required")
            if field not in {"pr_context", "pr_reference", "operation", "task"}:
                raise ValueError("pr_context_migration_required")
            target.pop("name", None)
            target.update(
                fieldName="pr_context", inputTypes=["Data", "Message"], type="other"
            )
        if edge["source"] in prs or edge["target"] in prs:
            edge.setdefault("data", {}).update(sourceHandle=source, targetHandle=target)
            edge["sourceHandle"] = json.dumps(source)
            edge["targetHandle"] = json.dumps(target)
    return result
