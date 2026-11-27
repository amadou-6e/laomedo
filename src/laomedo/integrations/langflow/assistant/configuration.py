"""Audited configuration discovery and no-execution readiness over existing owners."""

import asyncio
from collections import OrderedDict
import hashlib
import time
from uuid import UUID

from sqlmodel import select

from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.models import ConfigurationRequest
from laomedo.integrations.langflow.assistant.models import FlowDiagnostic
from laomedo.integrations.langflow.assistant.models import ResolvedConfiguration
from laomedo.integrations.langflow.assistant.models import ResourceBinding
from laomedo.integrations.langflow.assistant.models import NodeResourceBindings
from laomedo.integrations.langflow.assistant.models import RunResourceBinding
from laomedo.integrations.langflow.assistant.models import ConfigurationResult
from laomedo.integrations.langflow.assistant.models import WorkflowValidationResult
from laomedo.integrations.langflow.assistant.settings import AUDITED_AGENT_COMPONENTS
from laomedo.integrations.langflow.assistant.settings import RESOLUTION_LIMIT
from laomedo.integrations.langflow.assistant.settings import RESOLUTION_SECONDS


class WorkflowConfiguration:
    """Never evaluate component refresh hooks or accept a model-provided executable template."""

    def __init__(self, runtime):
        """Bind existing authorizing runtime; no account discovery at construction."""
        self.runtime = runtime
        self.resolutions = OrderedDict()

    def required_fields(self, catalog, identity):
        """Add audited runtime requirements absent from installed editor metadata."""
        fields = set(catalog.resolution_fields(identity))
        if catalog.audited_family(identity) == "LaomedoGitHubIssue":
            return {"repository_url", "issue_choice", "public_service_only"}
        if catalog.audited_family(identity) in AUDITED_AGENT_COMPONENTS:
            fields.add("task")
        return fields

    async def resolve(self, context, catalog, request: ConfigurationRequest):
        """Resolve only supported families using explicitly authorized resource owners."""
        await self.runtime.authorize(context)
        identity = request.component_type
        schema = catalog.schema_revision(identity)
        if request.schema_revision and request.schema_revision != schema:
            raise AssistantError("assistant_configuration_stale", 409)
        template = catalog.template(identity)["template"]
        name = catalog.audited_family(identity)
        values, options, resources = {}, {}, []
        dynamic = set()
        if name in AUDITED_AGENT_COMPONENTS:
            provider = AUDITED_AGENT_COMPONENTS[name]
            rows = await self.runtime.connections(context.owner_id)
            options["provider_connection"] = [
                row
                for row in rows["connections"]
                if row["provider"] == provider and row["lifecycle"] == "connected"
            ]
            dynamic = {"provider_connection", "model", "effort"}
            if request.connection_id is not None:
                self.runtime.check_connection(
                    context.owner_id,
                    provider,
                    request.connection_id,
                    request.connection_generation,
                )
                observed = await self.runtime.models(
                    context.owner_id,
                    provider,
                    request.connection_id,
                    request.connection_generation,
                )
                models = observed["models"]
                options["model"] = models
                values["provider_connection"] = str(request.connection_id)
                chosen = request.fields.get("model")
                if chosen is None and "effort" in request.fields:
                    raise AssistantError("assistant_configuration_required", 422)
                if chosen is not None:
                    selected = next(
                        (model for model in models if model["id"] == chosen), None
                    )
                    if selected is None:
                        raise AssistantError("assistant_model_unavailable", 422)
                    options["effort"] = selected["efforts"]
                    if request.fields.get("effort") not in (None, *selected["efforts"]):
                        raise AssistantError("assistant_model_unavailable", 422)
            elif any(field in request.fields for field in dynamic):
                raise AssistantError("assistant_configuration_required", 422)
        elif name == "LaomedoGitHubIssue":
            from laomedo.github.contract import labels_value, repository_from_url
            from laomedo.github.interface.issues.client import issue_request

            dynamic = {
                "repository_url",
                "labels",
                "state",
                "issue_choice",
                "public_service_only",
            }
            if request.fields.get("public_service_only", True) is not True:
                raise AssistantError("assistant_configuration_required", 422)
            values["public_service_only"] = True
            repository_url = request.fields.get("repository_url")
            if repository_url is not None:
                try:
                    repository_from_url(repository_url)
                    labels = labels_value(request.fields.get("labels", []))
                    state = request.fields.get("state", "open")
                    if state not in {"open", "closed", "all"}:
                        raise ValueError("issue_state_invalid")
                    found = await asyncio.to_thread(
                        issue_request,
                        "discover",
                        repository_url=repository_url,
                        labels=labels,
                        state=state,
                        public_only=True,
                    )
                    choices = [item["choice"] for item in found["issues"]]
                    if not isinstance(found["labels"], list) or not all(
                        isinstance(item, str) for item in choices
                    ):
                        raise ValueError("issue_discovery_invalid")
                except (ValueError, KeyError, TypeError):
                    raise AssistantError(
                        "assistant_resource_unavailable", 422
                    ) from None
                values.update(repository_url=repository_url, labels=labels, state=state)
                options.update(labels=found["labels"], issue_choice=choices)
                chosen = request.fields.get("issue_choice")
                if chosen is not None:
                    if chosen not in choices:
                        raise AssistantError("assistant_resource_unavailable", 422)
                    values["issue_choice"] = chosen
            elif any(
                key in request.fields for key in ("labels", "state", "issue_choice")
            ):
                raise AssistantError("assistant_configuration_required", 422)
        elif name == "LaomedoSkill":
            dynamic = {"skill_id", "revision_id"}
            observed = await self.runtime.skills(context)
            options["skills"] = observed
            if request.fields.get("skill_id") is not None:
                # Exact pinned revision is verified by the registry, not inferred from labels.
                from laomedo.skills.registry.store import SkillStore

                root = self.runtime.provider_connections.controllers.skill_store
                skill_id = request.fields["skill_id"]
                revision_id = request.fields.get("revision_id")
                store = SkillStore(root)
                revision = (
                    await asyncio.to_thread(store.revision, skill_id, revision_id)
                    if revision_id
                    else await asyncio.to_thread(store.revision, skill_id)
                )
                values.update(skill_id=skill_id, revision_id=revision["revision_id"])
                resources.append(
                    {
                        "kind": "skill",
                        "id": skill_id,
                        "version": revision["revision_id"],
                    }
                )
        elif name == "MCPTools":
            from langflow.services.database.models import MCPServer

            dynamic = {"mcp_server"}
            async with self.runtime.store.sessions() as session:
                rows = (
                    await session.exec(
                        select(MCPServer.id, MCPServer.name, MCPServer.version).where(
                            MCPServer.user_id == context.owner_id,
                            MCPServer.enabled == True,
                        )
                    )
                ).all()
            options["mcp_server"] = [
                {"id": str(row.id), "name": row.name, "version": row.version}
                for row in rows[:100]
            ]
            chosen = request.fields.get("mcp_server")
            if chosen is not None:
                selected = next((row for row in rows if str(row.id) == chosen), None)
                if selected is None:
                    raise AssistantError("assistant_resource_unavailable", 404)
                values["mcp_server"] = {"name": selected.name}
                resources.append(
                    {
                        "kind": "mcp",
                        "id": str(selected.id),
                        "version": str(selected.version),
                    }
                )
        for field, value in request.fields.items():
            if field not in template:
                raise AssistantError("assistant_field_unknown", 422)
            if field in values and (
                name != "LaomedoGitHubIssue" or values[field] == value
            ):
                continue
            if field in dynamic:
                if field == "provider_connection" and value != str(
                    request.connection_id
                ):
                    raise AssistantError("assistant_configuration_stale", 409)
                if field in {"model", "effort"} and request.connection_id is not None:
                    values[field] = value
                else:
                    raise AssistantError("assistant_configuration_required", 422)
            else:
                values[field] = catalog._value(field, template[field], value, identity)
        resolved = ResolvedConfiguration(
            owner_id=context.owner_id,
            conversation_id=context.conversation_id,
            session_key=context.session_key,
            component_type=identity,
            schema_revision=schema,
            fields=values,
            resources=resources,
            connection_id=request.connection_id,
            connection_generation=request.connection_generation,
            expires_at=time.time() + RESOLUTION_SECONDS,
        )
        await self.check(context, catalog, resolved)
        self.resolutions[resolved.id] = resolved
        now = time.time()
        for key in list(self.resolutions):
            if self.resolutions[key].expires_at <= now:
                self.resolutions.pop(key, None)
        while len(self.resolutions) > RESOLUTION_LIMIT:
            self.resolutions.popitem(last=False)
        await self.runtime.authorize(context)
        required = self.required_fields(catalog, identity)
        required.update(
            name
            for name, field in template.items()
            if isinstance(field, dict)
            and field.get("required")
            and name != "code"
            and not (name == "tool" and catalog.audited_family(identity) == "MCPTools")
        )
        missing = []
        for name in sorted(required):
            value = values.get(name)
            field = template.get(name, {})
            if (
                name not in values
                and name not in dynamic
                and catalog._writable(name, field)
            ):
                value = field.get("value")
            if value in (None, "", [], {}):
                missing.append(
                    FlowDiagnostic(
                        code="configuration_missing",
                        field=name,
                        message="Select a value or connect a compatible output.",
                    )
                )
        return ConfigurationResult(
            resolution_id=resolved.id,
            component_type=identity,
            schema_revision=schema,
            fields=values,
            options=options,
            expires_at=resolved.expires_at,
            remaining_requirements=missing,
            provenance={
                name: (
                    "resolved_owner"
                    if name in dynamic and name in values
                    else "requested_static" if name in values else "omitted"
                )
                for name in template
                if name != "code" and not name.startswith("_")
            },
        ).model_dump(mode="json")

    async def check(self, context, catalog, resolved, *, active=True):
        """Revalidate exact owner/schema/resource epochs without model/native discovery."""
        if active:
            await self.runtime.authorize(context)
        else:
            await self.runtime.check_session(context.owner_id, context.session_key)
        if (
            resolved.owner_id != context.owner_id
            or resolved.conversation_id != context.conversation_id
            or resolved.session_key != context.session_key
            or resolved.expires_at <= time.time()
            or resolved.schema_revision
            != catalog.schema_revision(resolved.component_type)
        ):
            raise AssistantError("assistant_configuration_stale", 409)
        provider = AUDITED_AGENT_COMPONENTS.get(
            catalog.audited_family(resolved.component_type)
        )
        if resolved.connection_id is not None:
            if provider is None:
                raise AssistantError("assistant_configuration_stale", 409)
            self.runtime.check_connection(
                context.owner_id,
                provider,
                resolved.connection_id,
                resolved.connection_generation,
            )
        await self.check_resources(context, resolved.resources)

    async def check_resources(self, context, resources):
        """Read current resource owners; never decrypt MCP configuration or load tool sessions."""
        for resource in resources:
            resource = ResourceBinding.model_validate(resource)
            if resource.kind == "mcp":
                from langflow.services.database.models import MCPServer

                async with self.runtime.store.sessions() as session:
                    row = (
                        await session.exec(
                            select(MCPServer.version).where(
                                MCPServer.id == UUID(resource.id),
                                MCPServer.user_id == context.owner_id,
                                MCPServer.enabled == True,
                            )
                        )
                    ).first()
                if row is None or str(row) != resource.version:
                    raise AssistantError("assistant_resource_unavailable", 409)
            elif resource.kind == "skill":
                from laomedo.skills.registry.store import SkillStore

                root = self.runtime.provider_connections.controllers.skill_store
                await asyncio.to_thread(
                    SkillStore(root).revision, resource.id, resource.version
                )
            else:
                raise AssistantError("assistant_resource_unavailable", 409)

    async def prepare(self, context, catalog, definitions, *, active=True):
        """Admit each provided resolution before the existing compiler/patch owner runs."""
        for definition in definitions:
            if definition.resolution_id is None:
                continue
            resolved = self.resolutions.get(definition.resolution_id)
            if resolved is None:
                raise AssistantError("assistant_configuration_stale", 409)
            await self.check(context, catalog, resolved, active=active)
            catalog.allow_resolution(resolved)

    def approval_deadline(self, definitions, latest):
        """Bound a prepared proposal by every referenced configuration's lifetime."""
        deadline = latest
        for definition in definitions:
            if definition.resolution_id is None:
                continue
            resolved = self.resolutions.get(definition.resolution_id)
            if resolved is None:
                raise AssistantError("assistant_configuration_stale", 409)
            deadline = min(deadline, resolved.expires_at)
        return deadline

    async def check_graph(self, context, catalog, data, *, active=True):
        """Fence persisted resource references at use without refreshing native catalogues."""
        if active:
            await self.runtime.authorize(context)
        else:
            await self.runtime.check_session(context.owner_id, context.session_key)
        nodes = {}
        for node in (data or {}).get("nodes", []):
            if (
                not isinstance(node, dict)
                or not isinstance(node.get("id"), str)
                or not isinstance(node.get("data"), dict)
                or node["id"] in nodes
            ):
                raise AssistantError("assistant_input_invalid", 422)
            nodes[node["id"]] = node
        for edge in (data or {}).get("edges", []):
            if not isinstance(edge, dict):
                continue
            details = edge.get("data") or {}
            handle = details.get("targetHandle") if isinstance(details, dict) else None
            target_id = edge.get("target")
            if not isinstance(target_id, str):
                raise AssistantError("assistant_input_invalid", 422)
            target = nodes.get(target_id, {})
            target_data = target.get("data")
            if (
                isinstance(handle, dict)
                and handle.get("fieldName") == "verified_changes"
                and isinstance(target_data, dict)
                and target_data.get("type") == "LaomedoClaudeAgent"
                and getattr(self.runtime, "graph_executor", None) is None
            ):
                raise AssistantError("verified_review_isolation_unavailable", 409)
        for node in (data or {}).get("nodes", []):
            node_data = node.get("data", {})
            template = node_data.get("node", {}).get("template", {})
            if node_data.get("type") == "LaomedoGitHubIssue":
                from laomedo.integrations.langflow.assistant.settings import (
                    AUDITED_COMPONENT_DIGESTS,
                )

                code = template.get("code", {}).get("value")
                if (
                    template.get("public_service_only", {}).get("value") is not True
                    or not isinstance(code, str)
                    or hashlib.sha256(
                        code.replace("\r\n", "\n").strip().encode()
                    ).hexdigest()
                    != AUDITED_COMPONENT_DIGESTS["LaomedoGitHubIssue"]
                ):
                    raise AssistantError("assistant_configuration_stale", 409)
            raw = node.get("data", {}).get("laomedo_authoring_bindings")
            if not raw:
                continue
            binding = NodeResourceBindings.model_validate(raw)
            identity = catalog.project({"nodes": [node]})["nodes"][0].get(
                "component_type", ""
            )
            provider = AUDITED_AGENT_COMPONENTS.get(catalog.audited_family(identity))
            if binding.connection_id:
                if provider is None:
                    raise AssistantError("assistant_resource_unavailable", 409)
                selected = binding.connection_id
                self.runtime.check_connection(
                    context.owner_id, provider, selected, binding.generation
                )
                saved = (
                    node["data"]["node"]["template"]
                    .get("provider_connection", {})
                    .get("value")
                )
                if saved != str(selected):
                    raise AssistantError("assistant_configuration_stale", 409)
            await self.check_resources(context, binding.resources)
            for resource in binding.resources:
                if resource.kind == "skill":
                    if (
                        template.get("skill_id", {}).get("value") != resource.id
                        or template.get("revision_id", {}).get("value")
                        != resource.version
                    ):
                        raise AssistantError("assistant_configuration_stale", 409)
                elif resource.kind == "mcp":
                    from langflow.services.database.models import MCPServer

                    async with self.runtime.store.sessions() as session:
                        server = await session.get(MCPServer, UUID(resource.id))
                        if (
                            server is None
                            or server.user_id != context.owner_id
                            or template.get("mcp_server", {}).get("value")
                            != {"name": server.name}
                        ):
                            raise AssistantError("assistant_configuration_stale", 409)

    async def binding_diagnostics(self, context, catalog, data):
        """Keep stale graphs inspectable without admitting stale values or execution."""
        await self.runtime.authorize(context)
        diagnostics = []
        for node in (data or {}).get("nodes", []):
            raw = node.get("data", {}).get("laomedo_authoring_bindings")
            if not raw and node.get("data", {}).get("type") != "LaomedoGitHubIssue":
                continue
            try:
                await self.check_graph(
                    context, catalog, {"nodes": [node]}, active=False
                )
            except AssistantError as error:
                if not error.code.startswith("provider_") and error.code not in {
                    "assistant_resource_unavailable",
                    "assistant_configuration_stale",
                    "assistant_setup_required",
                }:
                    raise
                diagnostics.append(
                    FlowDiagnostic(
                        code="binding_stale",
                        node_id=node["id"],
                        field=(
                            "provider_connection"
                            if isinstance(raw, dict) and raw.get("connection_id")
                            else None
                        ),
                        message="Select this node's account or resource again before running it.",
                    )
                )
            except ValueError:
                diagnostics.append(
                    FlowDiagnostic(
                        code="binding_invalid",
                        node_id=node["id"],
                        message="Select this node's account or resource again before running it.",
                    )
                )
        await self.runtime.authorize(context)
        return diagnostics

    async def project(self, context, catalog, data):
        """Expose safe structure and repair diagnostics while withholding stale selectors."""
        diagnostics = await self.binding_diagnostics(context, catalog, data)
        stale = {issue.node_id for issue in diagnostics}
        result = catalog.project(data)
        result["diagnostics"] = [issue.model_dump() for issue in diagnostics]
        saved = {node["id"]: node for node in (data or {}).get("nodes", [])}
        for node in result["nodes"]:
            source = saved.get(node["key"], {})
            if not source.get("data", {}).get("laomedo_authoring_bindings"):
                continue
            identity = node.get("component_type")
            if not identity or catalog.audited_family(identity) is None:
                continue
            descriptions = catalog.describe(identity)["inputs"]
            template = source.get("data", {}).get("node", {}).get("template", {})
            for field in descriptions:
                name = field["name"]
                if field["resolvable"]:
                    node["fields"].pop(name, None)
                if node["key"] in stale:
                    if field["resolvable"] and name not in node["unresolved_fields"]:
                        node["unresolved_fields"].append(name)
                    continue
                value = template.get(name, {}).get("value")
                safe = isinstance(value, str) and len(value) <= 200
                if (
                    name == "public_service_only"
                    and catalog.audited_family(identity) == "LaomedoGitHubIssue"
                ):
                    safe = value is True
                if (
                    name == "labels"
                    and catalog.audited_family(identity) == "LaomedoGitHubIssue"
                ):
                    safe = (
                        isinstance(value, list)
                        and len(value) <= 100
                        and all(
                            isinstance(item, str) and len(item) <= 100 for item in value
                        )
                    )
                if name == "mcp_server" and isinstance(value, dict):
                    safe = (
                        set(value) == {"name"}
                        and isinstance(value["name"], str)
                        and len(value["name"]) <= 200
                    )
                if field["resolvable"] and safe:
                    node["fields"][name] = value
                    node["unresolved_fields"] = [
                        item for item in node["unresolved_fields"] if item != name
                    ]
        await self.runtime.authorize(context)
        return result

    def graph_bindings(self, catalog, data):
        """Project resource fences without keeping graph inputs, code or configuration."""
        return [
            RunResourceBinding(
                component_type=catalog.project({"nodes": [node]})["nodes"][0][
                    "component_type"
                ],
                binding=NodeResourceBindings.model_validate(
                    node["data"]["laomedo_authoring_bindings"]
                ),
            ).model_dump(mode="json")
            for node in (data or {}).get("nodes", [])
            if node.get("data", {}).get("laomedo_authoring_bindings")
        ]

    async def check_bindings(self, context, catalog, bindings):
        """Recheck retained output authority against current account and resource epochs."""
        await self.runtime.authorize(context)
        for raw in bindings:
            value = RunResourceBinding.model_validate(raw)
            provider = AUDITED_AGENT_COMPONENTS.get(
                catalog.audited_family(value.component_type)
            )
            if value.binding.connection_id is not None:
                if provider is None:
                    raise AssistantError("assistant_resource_unavailable", 409)
                self.runtime.check_connection(
                    context.owner_id,
                    provider,
                    value.binding.connection_id,
                    value.binding.generation,
                )
            await self.check_resources(context, value.binding.resources)
        await self.runtime.authorize(context)

    async def validate(
        self, context, workflows, *, spec=None, workflow_id=None, expected_revision=None
    ):
        """Check metadata and bindings only; never instantiate/build/refresh a component."""
        await self.runtime.authorize(context)
        diagnostics = []
        if (spec is None) == (workflow_id is None):
            raise AssistantError("assistant_input_invalid", 422)
        if spec is not None:
            await self.prepare(context, workflows.catalog, spec.nodes)
            data, messages = workflows.catalog.compile(
                spec.model_copy(update={"allow_incomplete": True})
            )
            diagnostics.extend(
                FlowDiagnostic(
                    code=(
                        "default_omitted"
                        if text.startswith("warning: ")
                        else "configuration_missing"
                    ),
                    severity="warning" if text.startswith("warning: ") else "error",
                    message=text[:500],
                )
                for text in messages
            )
            revision = None
        else:
            from laomedo.integrations.langflow.assistant.actions import WorkflowActions

            actions = WorkflowActions(
                workflows.store, workflows.catalog, workflows.authorize
            )
            async with workflows.store.sessions() as session:
                await workflows.store.authorize(
                    session, context.owner_id, context.session_key
                )
                flow = await actions.flow(session, context.owner_id, workflow_id)
                revision = workflows.revision(flow)
                if expected_revision != revision:
                    raise AssistantError("assistant_source_revision_changed", 409)
                data = flow.data
        connected = set()
        for edge in data.get("edges", []):
            if not isinstance(edge, dict):
                continue
            details = edge.get("data")
            handle = details.get("targetHandle") if isinstance(details, dict) else None
            if (
                isinstance(handle, dict)
                and isinstance(edge.get("target"), str)
                and isinstance(handle.get("fieldName"), str)
            ):
                connected.add((edge.get("target"), handle.get("fieldName")))
        from laomedo.integrations.langflow.assistant.graph import GraphEditor
        from laomedo.integrations.langflow.assistant.models import GraphConnection

        nodes = {node["id"]: node for node in data.get("nodes", [])}
        for node_id, field in connected:
            node = nodes.get(node_id, {})
            if (
                field == "verified_changes"
                and node.get("data", {}).get("type") == "LaomedoClaudeAgent"
                and getattr(self.runtime, "graph_executor", None) is None
            ):
                diagnostics.append(
                    FlowDiagnostic(
                        code="verified_review_isolation_unavailable",
                        node_id=node_id,
                        field=field,
                        message="Secure review is not available in this installation.",
                    )
                )
        for edge in data.get("edges", []):
            try:
                definition = GraphConnection(
                    source=edge["source"],
                    target=edge["target"],
                    output=edge.get("data", {}).get("sourceHandle", {}).get("name"),
                    input=edge.get("data", {}).get("targetHandle", {}).get("fieldName"),
                )
                GraphEditor(workflows.catalog).connection(definition, nodes)
            except (AssistantError, ValueError, KeyError, TypeError, AttributeError):
                diagnostics.append(
                    FlowDiagnostic(
                        code="invalid_connection",
                        message="A connection must use existing compatible named ports.",
                    )
                )
        diagnostics.extend(
            await self.binding_diagnostics(context, workflows.catalog, data)
        )
        for node in data.get("nodes", []):
            identity = workflows.catalog.project({"nodes": [node]})["nodes"][0]
            if identity.get("unsupported"):
                diagnostics.append(
                    FlowDiagnostic(
                        code="unsupported_component",
                        node_id=node["id"],
                        message="Installed component metadata is unavailable.",
                    )
                )
                continue
            required = self.required_fields(
                workflows.catalog, identity["component_type"]
            )
            for field, metadata in (
                node.get("data", {}).get("node", {}).get("template", {}).items()
            ):
                if (
                    isinstance(metadata, dict)
                    and (metadata.get("required") or field in required)
                    and metadata.get("value") in (None, "", [])
                    and (node["id"], field) not in connected
                ):
                    diagnostics.append(
                        FlowDiagnostic(
                            code="required_input_missing",
                            node_id=node["id"],
                            field=field,
                            message="Select a value or connect a compatible output.",
                        )
                    )
        executor = getattr(self.runtime, "graph_executor", None)
        if executor is not None:
            from laomedo.agents.connections.errors import ProviderConnectionError
            from laomedo.github.node_runs.errors import GitHubNodeAuthorizationError
            from laomedo.integrations.langflow.execution.worker.errors import (
                GraphWorkerError,
            )

            try:
                await self.runtime.plan_graph(context, workflow_id, data)
            except (
                ProviderConnectionError,
                GitHubNodeAuthorizationError,
                GraphWorkerError,
                ValueError,
            ):
                diagnostics.append(
                    FlowDiagnostic(
                        code="isolated_graph_unsupported",
                        message="This configuration is unavailable in the isolated runner.",
                    )
                )
        await self.runtime.authorize(context)
        return WorkflowValidationResult(
            workflow_id=workflow_id,
            revision=revision,
            ready=not any(issue.severity == "error" for issue in diagnostics),
            diagnostics=diagnostics,
        ).model_dump(mode="json")
