"""Pure projection and compilation of already installed component metadata."""

from copy import deepcopy
import json
import math
import re
import hashlib

from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.settings import AUDITED_COMPONENT_DIGESTS


class ComponentCatalog:
    """Never import component code, instantiate a graph or call a dynamic update hook."""

    def __init__(self, snapshot):
        """Bind an already authorized installed metadata snapshot, without evaluating code."""
        self.snapshot = snapshot
        self.resolutions = {}

    def schema_revision(self, identity):
        """Identify exact installed metadata/source without exposing its contents."""
        return (
            "sha256:"
            + hashlib.sha256(
                json.dumps(
                    self.template(identity), sort_keys=True, default=str
                ).encode()
            ).hexdigest()
        )

    def audited_family(self, identity):
        """Require exact reviewed installed source, not a forgeable component class name."""
        component = self._index().get(identity, {})
        name = component.get("name") or identity.split("/", 1)[-1]
        expected = (
            AUDITED_COMPONENT_DIGESTS.get(name) if isinstance(name, str) else None
        )
        code = component.get("template", {}).get("code", {}).get("value")
        if (
            expected
            and isinstance(code, str)
            and hashlib.sha256(code.replace("\r\n", "\n").strip().encode()).hexdigest()
            == expected
        ):
            return name
        return None

    def resolution(self, identifier, identity, fields):
        """Bind only an already host-validated resolution to exact node values."""
        resolved = self.resolutions.get(identifier)
        if (
            resolved is None
            or resolved.component_type != identity
            or resolved.schema_revision != self.schema_revision(identity)
        ):
            raise AssistantError("assistant_configuration_stale", 409)
        if any(fields.get(name) != value for name, value in resolved.fields.items()):
            raise AssistantError("assistant_configuration_stale", 409)
        return resolved

    def allow_resolution(self, resolved):
        """Admit exact audited values, never arbitrary field names or provider credentials."""
        self.resolutions[resolved.id] = resolved

    @classmethod
    async def from_installed(cls, owner):
        """Read only initialized metadata and apply the app's real catalog/provider policies."""
        from lfx.interface.components import component_cache
        from langflow.services.deps import get_catalog_policy_service
        from langflow.api.v1.endpoints import (
            _filter_component_palette_by_catalog_policy,
            _filter_component_palette_by_provider_policy,
        )

        with component_cache.state_lock:
            if (
                not component_cache.all_types_ready
                or component_cache.all_types_dict is None
            ):
                raise AssistantError("assistant_catalog_unavailable", 503)
            snapshot = {
                category: dict(values)
                for category, values in component_cache.all_types_dict.items()
            }
            snapshot = _filter_component_palette_by_catalog_policy(
                snapshot,
                blocked_component_keys=get_catalog_policy_service().snapshot.blocked_component_keys,
                component_identity_index=component_cache.component_identity_index,
            )
        snapshot = await _filter_component_palette_by_provider_policy(
            snapshot, user_id=owner
        )
        return cls(snapshot)

    def _index(self):
        """Use category-qualified identities so duplicate component names never collide."""
        result = {}
        for category, components in self.snapshot.items():
            if not isinstance(components, dict):
                continue
            for name, component in components.items():
                if isinstance(component, dict):
                    result[category + "/" + name] = component
        return result

    def search(self, query, cursor=0):
        """Return bounded non-code descriptions; unavailable lazy templates are explicit."""
        if len(query) > 200 or cursor < 0 or cursor > 10000:
            raise AssistantError("assistant_input_invalid", 400)
        matches = []
        for identity, component in sorted(self._index().items()):
            label = str(component.get("display_name") or identity)[:200]
            description = str(component.get("description") or "")[:1500]
            if (
                query.casefold()
                in (identity + " " + label + " " + description).casefold()
            ):
                matches.append(
                    {
                        "component_type": identity,
                        "display_name": label,
                        "description": description,
                        "metadata_available": isinstance(
                            component.get("template"), dict
                        ),
                    }
                )
        return {
            "components": matches[cursor : cursor + 20],
            "next_cursor": cursor + 20 if len(matches) > cursor + 20 else None,
        }

    def template(self, identity):
        """Resolve trusted installed bytes; a saved/model-supplied template is never accepted."""
        component = self._index().get(identity)
        if (
            sum(
                key.split("/", 1)[1] == identity.split("/", 1)[-1]
                for key in self._index()
            )
            > 1
        ):
            raise AssistantError("assistant_component_identity_ambiguous", 422)
        if (
            component is None
            or not isinstance(component.get("template"), dict)
            or not isinstance(component.get("outputs"), list)
        ):
            raise AssistantError("assistant_component_metadata_unavailable", 422)
        if not isinstance(component["template"].get("code", {}).get("value"), str):
            raise AssistantError("assistant_component_metadata_unavailable", 422)
        result = deepcopy(component)
        if self.audited_family(identity) == "MCPTools" and not any(
            output.get("name") == "component_as_tool" for output in result["outputs"]
        ):
            result["outputs"].append(
                {
                    "name": "component_as_tool",
                    "display_name": "Toolset",
                    "method": "to_toolkit",
                    "types": ["Tool"],
                    "cache": False,
                }
            )
        return result

    def _protected_field(self, name, field):
        """Own the common credential/code/raw host-selector policy for values and edges."""
        if not isinstance(field, dict):
            return True
        normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).casefold()
        return (
            name.startswith("_")
            or name
            in {
                "code",
                "source",
                "path",
                "file_path",
                "directory",
                "command",
                "headers",
                "mcp_servers",
            }
            or bool(field.get("password"))
            or any(
                part in normalized
                for part in ("password", "secret", "token", "api_key", "credential")
            )
            or bool(
                re.search(
                    r"(^|_)(url|uri|endpoint|host|hostname|proxy|webhook|server|address|base|kwargs|config|settings|connection|environment|env|headers|authorization)(_|$)",
                    normalized,
                )
            )
        )

    def _writable(self, name, field):
        """Admit plain static settings only; capability references remain host-owned."""
        return (
            not self._protected_field(name, field)
            and name not in {"mcp_registration", "run_reference", "run_reference_json"}
            and field.get("show") is not False
            and not field.get("load_from_db")
            and not field.get("real_time_refresh")
            and not field.get("dynamic")
            and field.get("type") in {"str", "int", "float", "bool"}
        )

    def _connectable(self, name, field):
        """Reject protected raw selectors while preserving typed capability ports.

        Run-reference and MCP-registration connections are validated by their
        owning services, rather than interpreted as model-supplied host settings.
        """
        return not self._protected_field(name, field)

    def resolution_fields(self, identity):
        """Own audited dependency roles even when installed dropdown metadata is empty."""
        family = self.audited_family(identity)
        return (
            {
                "provider_connection": [],
                "model": ["provider_connection"],
                "effort": ["provider_connection", "model"],
            }
            if family
            in {"LaomedoCodexAgent", "LaomedoClaudeAgent", "LaomedoOpenCodeAgent"}
            else (
                {"skill_id": [], "revision_id": ["skill_id"]}
                if family == "LaomedoSkill"
                else {"mcp_server": []} if family == "MCPTools" else {}
            )
        )

    def describe(self, identity):
        """Expose installed constraints without private defaults or executable source."""
        component = self.template(identity)
        family = self.audited_family(identity)
        dynamic = self.resolution_fields(identity)
        inputs = []
        for name, field in component["template"].items():
            if name.startswith("_") or not isinstance(field, dict) or name == "code":
                continue
            inputs.append(
                {
                    "name": name,
                    "display_name": str(field.get("display_name") or name)[:200],
                    "type": field.get("type"),
                    "input_types": field.get("input_types") or [],
                    "required": bool(field.get("required")),
                    "list": bool(field.get("list")),
                    "writable": self._writable(name, field) and name not in dynamic,
                    "resolvable": name in dynamic,
                    "depends_on": dynamic.get(name, []),
                    "kind": (
                        "static"
                        if self._writable(name, field) and name not in dynamic
                        else (
                            "dynamic"
                            if field.get("dynamic") or field.get("real_time_refresh")
                            else (
                                "resource"
                                if field.get("load_from_db")
                                else "unsupported"
                            )
                        )
                    ),
                    "blocked_reason": (
                        None
                        if self._writable(name, field) and name not in dynamic
                        else (
                            "requires_audited_resolution"
                            if name in dynamic
                            else "field_not_supported"
                        )
                    ),
                    "default_provenance": (
                        "installed_static"
                        if self._writable(name, field) and name not in dynamic
                        else "not_copied"
                    ),
                    "connectable": self._connectable(name, field),
                    "options": (
                        field.get("options", [])[:100]
                        if self._writable(name, field) and name not in dynamic
                        else []
                    ),
                    "description": str(field.get("info") or "")[:1000],
                }
            )
        return {
            "component_type": identity,
            "configuration_support": (
                "audited_adapter" if family else "static_fields_only"
            ),
            "schema_revision": self.schema_revision(identity),
            "display_name": str(component.get("display_name") or identity)[:200],
            "description": str(component.get("description") or "")[:1500],
            "inputs": inputs,
            "outputs": [
                {"name": output["name"], "types": output.get("types", [])}
                for output in component["outputs"]
                if isinstance(output, dict) and isinstance(output.get("name"), str)
            ],
        }

    def _value(self, name, field, value, identity=None, *, resolved=None):
        """Check the exact static type without string coercion or executable validation."""
        if (
            resolved is not None
            and self.resolutions.get(resolved.id) is resolved
            and resolved.component_type == identity
            and name in resolved.fields
            and resolved.fields[name] == value
        ):
            return deepcopy(value)
        if (
            identity is not None and name in self.resolution_fields(identity)
        ) or not self._writable(name, field):
            raise AssistantError("assistant_field_not_writable", 422)
        values = value if field.get("list") else [value]
        if field.get("list") and (not isinstance(value, list) or len(value) > 100):
            raise AssistantError("assistant_field_type_invalid", 422)
        for item in values:
            kind = field["type"]
            valid = (
                (kind == "str" and isinstance(item, str) and len(item) <= 12000)
                or (kind == "int" and type(item) is int)
                or (
                    kind == "float"
                    and type(item) in (int, float)
                    and math.isfinite(item)
                )
                or (kind == "bool" and type(item) is bool)
            )
            if not valid or (field.get("options") and item not in field["options"]):
                raise AssistantError("assistant_field_type_invalid", 422)
        return deepcopy(value)

    def _set_resolved_value(self, identity, name, field, value):
        """Present only the verified selected string, never a cached account catalogue."""
        field["value"] = value
        field["show"] = True
        if name in self.resolution_fields(identity) and isinstance(value, str):
            field["options"] = [value] if value else []
            if "options_metadata" in field:
                field["options_metadata"] = [{}] if value else []

    def update_saved_fields(self, node, identity, values, *, resolved=None):
        """Change only explicit writable values, retaining saved code, secrets and schema."""
        metadata = self.template(identity)
        saved = node.get("data", {}).get("node", {}).get("template", {})
        preview = []
        for name, value in values.items():
            field = metadata["template"].get(name)
            original = saved.get(name)
            if (
                not isinstance(field, dict)
                or not isinstance(original, dict)
                or (not self._writable(name, original) and resolved is None)
            ):
                raise AssistantError("assistant_field_not_writable", 422)
            checked = self._value(name, field, value, identity, resolved=resolved)
            if original.get("type") != field.get("type"):
                raise AssistantError("assistant_field_type_invalid", 422)
            before = (
                self._value(name, field, original.get("value"), identity)
                if original.get("value") is not None
                and self._writable(name, original)
                and name not in self.resolution_fields(identity)
                else None
            )
            preview.append(
                "Set "
                + node["id"]
                + "."
                + name
                + ": "
                + json.dumps(before, ensure_ascii=False)
                + " -> "
                + json.dumps(checked, ensure_ascii=False)
            )
            original["value"] = checked
            if resolved is not None and name in resolved.fields:
                self._set_resolved_value(identity, name, original, checked)
            if not self._writable(name, field):
                original["show"] = True
        if resolved is not None:
            dependencies = self.resolution_fields(identity)
            invalidated = set(resolved.fields)
            while True:
                dependents = {
                    name
                    for name, parents in dependencies.items()
                    if name not in invalidated and invalidated.intersection(parents)
                }
                if not dependents:
                    break
                invalidated.update(dependents)
            for name in sorted(invalidated - set(resolved.fields)):
                if isinstance(saved.get(name), dict):
                    saved[name]["value"] = (
                        "" if saved[name].get("type") == "str" else None
                    )
                    saved[name]["options"] = []
                    if "options_metadata" in saved[name]:
                        saved[name]["options_metadata"] = []
                    preview.append("Clear " + node["id"] + "." + name)
        return preview

    def compile(self, graph):
        """Build editable node JSON from host templates; validate exact ports without graph construction."""
        if len(graph.model_dump_json().encode()) > 65536:
            raise AssistantError("assistant_graph_too_large", 422)
        nodes, by_key, diagnostics = [], {}, []
        for index, definition in enumerate(graph.nodes):
            if definition.key in by_key:
                raise AssistantError("assistant_duplicate_node", 422)
            template = self.template(definition.component_type)
            resolved = (
                self.resolution(
                    definition.resolution_id,
                    definition.component_type,
                    definition.fields,
                )
                if definition.resolution_id
                else None
            )
            if (
                resolved is not None
                and self.audited_family(definition.component_type) == "MCPTools"
            ):
                template["tool_mode"] = True
                if "tool" in template["template"]:
                    template["template"]["tool"]["required"] = False
            # Clear all non-code values before applying host-approved defaults or
            # model settings. Cached user-specific selectors are never copied.
            for name, field in template["template"].items():
                if not isinstance(field, dict) or name == "code":
                    continue
                if not self._writable(name, field) or name in self.resolution_fields(
                    definition.component_type
                ):
                    if field.get("value") is not None and field.get("value") not in (
                        "",
                        [],
                        {},
                    ):
                        diagnostics.append(
                            "warning: "
                            + definition.key
                            + "."
                            + name
                            + ": private or unsupported installed value omitted"
                        )
                    dynamic = name in self.resolution_fields(definition.component_type)
                    field["value"] = (
                        "" if dynamic and field.get("type") == "str" else None
                    )
                    if dynamic:
                        if "options" in field:
                            field["options"] = []
                        if "options_metadata" in field:
                            field["options_metadata"] = []
                elif "value" in field:
                    try:
                        field["value"] = self._value(name, field, field["value"])
                    except AssistantError:
                        if field.get("value") is not None and field.get(
                            "value"
                        ) not in ("", [], {}):
                            diagnostics.append(
                                "warning: "
                                + definition.key
                                + "."
                                + name
                                + ": unsupported installed default omitted"
                            )
                        field["value"] = None
            for name, value in definition.fields.items():
                field = template["template"].get(name)
                if not isinstance(field, dict):
                    raise AssistantError("assistant_field_unknown", 422)
                field["value"] = self._value(
                    name, field, value, definition.component_type, resolved=resolved
                )
                if resolved is not None and name in resolved.fields:
                    self._set_resolved_value(
                        definition.component_type, name, field, field["value"]
                    )
            component_name = definition.component_type.split("/", 1)[1]
            identifier = component_name + "-" + definition.key
            node = {
                "id": identifier,
                "type": "genericNode",
                "position": {"x": (index % 3) * 420, "y": (index // 3) * 400},
                "data": {"id": identifier, "type": component_name, "node": template},
            }
            if resolved is not None:
                node["data"]["laomedo_authoring_bindings"] = {
                    "connection_id": (
                        str(resolved.connection_id) if resolved.connection_id else None
                    ),
                    "generation": resolved.connection_generation,
                    "resources": [
                        resource.model_dump() for resource in resolved.resources
                    ],
                }
            by_key[definition.key] = node
            nodes.append(node)
        edges, targets, identities = [], set(), set()
        for edge in graph.edges:
            source, target = by_key.get(edge.source), by_key.get(edge.target)
            if source is None or target is None:
                raise AssistantError("assistant_edge_node_unknown", 422)
            output = next(
                (
                    item
                    for item in source["data"]["node"]["outputs"]
                    if item.get("name") == edge.output
                ),
                None,
            )
            field = target["data"]["node"]["template"].get(edge.input)
            if output is None or not self._connectable(edge.input, field):
                raise AssistantError("assistant_port_unknown", 422)
            accepted = field.get("input_types") or [field.get("type")]
            if not set(output.get("types") or []).intersection(accepted):
                raise AssistantError("assistant_port_incompatible", 422)
            identity = (edge.source, edge.output, edge.target, edge.input)
            if identity in identities or (
                (edge.target, edge.input) in targets and not field.get("list")
            ):
                raise AssistantError("assistant_edge_conflict", 422)
            identities.add(identity)
            targets.add((edge.target, edge.input))
            outgoing = {
                "dataType": source["data"]["type"],
                "id": source["id"],
                "name": edge.output,
                "output_types": output.get("types", []),
            }
            incoming = {
                "fieldName": edge.input,
                "id": target["id"],
                "inputTypes": field.get("input_types", []),
                "type": field.get("type"),
            }
            edges.append(
                {
                    "id": "edge-" + str(len(edges)),
                    "source": source["id"],
                    "target": target["id"],
                    "sourceHandle": json.dumps(outgoing),
                    "targetHandle": json.dumps(incoming),
                    "data": {"sourceHandle": outgoing, "targetHandle": incoming},
                }
            )
        for definition in graph.nodes:
            for name, field in by_key[definition.key]["data"]["node"][
                "template"
            ].items():
                if (
                    isinstance(field, dict)
                    and field.get("required")
                    and field.get("value") in (None, "", [])
                    and (definition.key, name) not in targets
                ):
                    diagnostics.append(
                        definition.key
                        + "."
                        + name
                        + ": required setting or connection missing"
                    )
        if (
            any(not message.startswith("warning: ") for message in diagnostics)
            and not graph.allow_incomplete
        ):
            raise AssistantError("assistant_draft_incomplete", 422)
        return {
            "nodes": nodes,
            "edges": edges,
            "viewport": {"x": 50, "y": 50, "zoom": 0.8},
        }, diagnostics

    def project(self, data):
        """Describe saved nodes without copying saved code, secret fields or arbitrary nested metadata."""
        nodes, identities = [], {}
        index = self._index()
        for node in (data or {}).get("nodes", [])[:40]:
            native_type = node.get("data", {}).get("type")
            matches = [key for key in index if key.split("/", 1)[1] == native_type]
            if len(matches) != 1:
                nodes.append(
                    {"key": str(node.get("id", ""))[:200], "unsupported": True}
                )
                continue
            metadata = self.template(matches[0])
            fields = {}
            unresolved = []
            saved = node.get("data", {}).get("node", {}).get("template", {})
            for name, field in metadata["template"].items():
                if self._writable(name, field) and isinstance(saved.get(name), dict):
                    try:
                        fields[name] = self._value(
                            name, field, saved[name].get("value")
                        )
                    except AssistantError:
                        if saved[name].get("value") is not None and saved[name].get(
                            "value"
                        ) not in ("", [], {}):
                            unresolved.append(name)
                elif (
                    isinstance(saved.get(name), dict)
                    and saved[name].get("value") is not None
                    and saved[name].get("value") not in ("", [], {})
                ):
                    if name != "code" and not name.startswith("_"):
                        unresolved.append(name)
            identifier = str(node.get("id", ""))[:200]
            identities[identifier] = True
            nodes.append(
                {
                    "key": identifier,
                    "component_type": matches[0],
                    "fields": fields,
                    "unresolved_fields": unresolved,
                }
            )
        edges = []
        for edge in (data or {}).get("edges", [])[:100]:
            handles = edge.get("data", {})
            output, field = handles.get("sourceHandle", {}), handles.get(
                "targetHandle", {}
            )
            if edge.get("source") in identities and edge.get("target") in identities:
                edges.append(
                    {
                        "source": edge["source"],
                        "output": str(output.get("name", ""))[:100],
                        "target": edge["target"],
                        "input": str(field.get("fieldName", ""))[:100],
                    }
                )
        return {"nodes": nodes, "edges": edges}
