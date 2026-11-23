"""Explicit portable graph synchronization through existing Flow ownership guards."""

from copy import deepcopy
import json

from sqlmodel import select

from laomedo.integrations.langflow.assistant.catalog import ComponentCatalog
from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.models import DraftGraph
from laomedo.integrations.langflow.assistant.storage.models import PortableGraph
from laomedo.integrations.langflow.assistant.workflows import WorkflowDrafts


class ProjectGraphs:
    """Keep graph file effects explicit and separate from normal editor autosave."""

    def __init__(self, runtime):
        self.runtime = runtime
        self.files = runtime.project_storage

    async def list(self, owner):
        from langflow.services.database.models.flow.model import Flow

        async with self.runtime.store.sessions() as session:
            rows = (
                await session.exec(
                    select(Flow)
                    .where(Flow.user_id == owner, Flow.is_component.is_not(True))
                    .order_by(Flow.name)
                    .limit(200)
                )
            ).all()
            revisions = WorkflowDrafts(None, None, None)
            return [
                {
                    "id": str(row.id),
                    "name": row.name,
                    "revision": revisions.revision(row),
                }
                for row in rows
            ]

    async def sync(self, owner, key, identifier, request, *, load=False):
        from langflow.services.database.models.flow.model import Flow
        from langflow.services.database.models.flow.guards import lock_flow_for_update

        catalog = await ComponentCatalog.from_installed(owner)
        revisions = WorkflowDrafts(None, catalog, None)
        async with self.runtime.store.transaction() as session:
            await self.runtime.store.authorize(session, owner, key)
            flow = await session.get(Flow, identifier)
            if flow is None or flow.user_id != owner:
                raise AssistantError("assistant_workflow_not_found", 404)
            await lock_flow_for_update(session, flow)
            if revisions.revision(flow) != request.expected_graph_revision:
                raise AssistantError("assistant_source_revision_changed", 409)
            if load and getattr(flow, "locked", False):
                raise AssistantError("assistant_storage_graph_locked", 409)
            await self.runtime.check_session(owner, key)
            with self.files.lock:
                path = self.files.graph_path(owner, request.location)
                document = self.files.document(owner)
                if any(
                    identity != str(identifier) and binding.location == request.location
                    for identity, binding in document.graphs.items()
                ):
                    raise AssistantError("assistant_storage_location_conflict", 409)
                digest = self.files.digest(path)
                if digest != request.expected_file_hash:
                    raise AssistantError("assistant_storage_file_changed", 409)
                diagnostics = []
                if load:
                    if digest is None:
                        raise AssistantError("assistant_storage_file_missing", 404)
                    try:
                        value = PortableGraph.model_validate_json(
                            path.read_text(encoding="utf-8")
                        )
                        if value.workflow_id != identifier or len(
                            set(value.node_ids.values())
                        ) != len(value.node_ids):
                            raise ValueError()
                        graph = value.spec
                    except (ValueError, UnicodeError, TypeError):
                        raise AssistantError(
                            "assistant_storage_graph_invalid", 422
                        ) from None
                    compiled, diagnostics = catalog.compile(graph)
                    old = {
                        node["id"]: node for node in (flow.data or {}).get("nodes", [])
                    }
                    identities = {}
                    for definition, node in zip(graph.nodes, compiled["nodes"]):
                        previous_id = value.node_ids.get(definition.key)
                        previous = old.get(previous_id)
                        if (
                            previous is None
                            or previous.get("data", {}).get("type")
                            != node["data"]["type"]
                        ):
                            continue
                        identities[node["id"]] = previous_id
                        node["id"] = node["data"]["id"] = previous_id
                        node["position"] = deepcopy(
                            previous.get("position", node["position"])
                        )
                        fields = (
                            previous.get("data", {}).get("node", {}).get("template", {})
                        )
                        for name, field in fields.items():
                            if isinstance(field, dict) and not catalog._writable(
                                name, field
                            ):
                                node["data"]["node"]["template"][name] = deepcopy(field)
                    for edge in compiled["edges"]:
                        for end, handle in (
                            ("source", "sourceHandle"),
                            ("target", "targetHandle"),
                        ):
                            edge[end] = identities.get(edge[end], edge[end])
                            metadata = edge["data"][handle]
                            metadata["id"] = edge[end]
                            edge[handle] = json.dumps(metadata)
                    compiled["viewport"] = deepcopy(
                        (flow.data or {}).get("viewport", compiled["viewport"])
                    )
                    flow.data = compiled
                    # A load updates graph contents only; name and app metadata stay owned by the app.
                    session.add(flow)
                    await session.flush()
                else:
                    data = flow.data or {}
                    if (
                        len(data.get("nodes", [])) > 40
                        or len(data.get("edges", [])) > 100
                    ):
                        raise AssistantError("assistant_graph_too_large", 422)
                    projected = catalog.project(data)
                    if any(
                        node.get("unsupported") for node in projected["nodes"]
                    ) or len(projected["edges"]) != len(data.get("edges", [])):
                        raise AssistantError("assistant_storage_graph_invalid", 422)
                    node_ids = {
                        "n" + str(index): original["id"]
                        for index, original in enumerate(data.get("nodes", []))
                    }
                    keys = {identity: key for key, identity in node_ids.items()}
                    if len(keys) != len(node_ids):
                        raise AssistantError("assistant_storage_graph_invalid", 422)
                    for node in projected["nodes"]:
                        if node.pop("unresolved_fields", []):
                            diagnostics.append(
                                node["key"] + ": app-managed settings omitted from file"
                            )
                        node["key"] = keys[node["key"]]
                    for edge in projected["edges"]:
                        edge["source"] = keys[edge["source"]]
                        edge["target"] = keys[edge["target"]]
                    projected["allow_incomplete"] = True
                    graph = DraftGraph.model_validate(projected)
                    value = PortableGraph(
                        workflow_id=identifier,
                        name=flow.name,
                        spec=graph,
                        node_ids=node_ids,
                    )
                    self.files.replace(
                        path, (value.model_dump_json(indent=2) + "\n").encode()
                    )
                    digest = self.files.digest(path)
                # File and DB are distinct stores. A metadata error is reported and never
                # presented as synchronized; the existing saved app graph remains available.
                self.files.bind_graph(owner, identifier, request.location, digest)
            return {
                "sha256": digest,
                "diagnostics": diagnostics,
                "revision": revisions.revision(flow),
                "loaded": load,
            }
