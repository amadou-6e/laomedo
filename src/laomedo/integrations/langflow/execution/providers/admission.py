"""Derive saved-provider execution bounds from a trusted effective graph snapshot."""

import re
import time
from pathlib import Path
from uuid import UUID
from pydantic import ValidationError

from laomedo.agents.connections.errors import ProviderConnectionError
from laomedo.agents.connections.models import (
    GraphNodePolicy,
    GraphRunNode,
    GraphRunPlan,
)
from laomedo.github.contract import repository_from_url, labels_value
from laomedo.github.node_runs.authority import GitHubRunAuthority
from laomedo.integrations.langflow.assistant.models import NodeResourceBindings
from laomedo.integrations.langflow.graph_admission.models import ResourceBinding
from laomedo.skills.registry.errors import SkillStoreError
from laomedo.skills.registry.models import SkillReference
from laomedo.skills.registry.store import SkillStore
from laomedo.integrations.langflow.graph_admission.node_runs import (
    GitHubNodeRunAdmission,
)
from laomedo.integrations.langflow.execution.providers.models import (
    GraphMcpSelection,
    PreparedProviderGraph,
    ProviderNodeRoute,
    ProviderWorkerJob,
    PublicIssueSelection,
)
from laomedo.integrations.langflow.graph_admission.models import GitHubCatalogSnapshot


class ProviderGraphAdmission:
    """Use host-authenticated ownership and immutable installed source identities.

    This object is composed in the API-only broker. A worker never supplies its
    profile, lease, account, catalog, deadline or native request identity.
    """

    AGENTS = {
        "LaomedoCodexAgent": "codex",
        "LaomedoClaudeAgent": "claude",
        "LaomedoOpenCodeAgent": "opencode",
    }
    PLUMBING = frozenset(
        {"TextInput", "TextOutput", "Prompt", "Prompt Template", "CombineText"}
    )

    def __init__(self, connections, catalog, *, skill_store: Path | None = None):
        self.connections = connections
        self.catalog = catalog
        self.skill_store = skill_store

    @staticmethod
    def _value(template, field, default=None):
        item = template.get(field, {})
        if not isinstance(item, dict) or item.get("load_from_db"):
            raise ProviderConnectionError("verified_review_unavailable")
        return item.get("value", default)

    def _node(self, owner, flow_id, node, provider, review_source, connected, skills):
        data = node["data"]
        template = data["node"]["template"]
        value = self._value
        if value(template, "operation", "fresh") not in {"fresh", "start"}:
            raise ProviderConnectionError("verified_review_unavailable")
        if any(
            value(template, field) not in (None, "", [])
            for field in (
                "run_reference",
                "run_reference_json",
                "skill_reference",
                "mcp_tools",
                "mcp_servers",
                "handoff_reference",
                "output_requirements",
                "output_requirements_json",
            )
        ):
            raise ProviderConnectionError("verified_review_unavailable")
        selected = value(template, "provider_connection")
        if not selected:
            selected = getattr(
                self.connections.graph_preferences(owner, flow_id), provider
            )
        record = self.connections.admitted(owner, UUID(str(selected)))
        if record.provider != provider:
            raise ProviderConnectionError("verified_review_unavailable")
        binding = NodeResourceBindings.model_validate(
            data.get("laomedo_authoring_bindings") or {}
        )
        if binding.resources or (
            binding.connection_id is not None
            and (
                binding.connection_id != record.connection_id
                or binding.generation != record.generation
            )
        ):
            raise ProviderConnectionError("verified_review_unavailable")
        if value(template, "verified_changes") not in (None, "", []):
            raise ProviderConnectionError("verified_review_unavailable")
        references = (
            (skills[connected["skill_reference"]],)
            if "skill_reference" in connected
            else ()
        )
        if review_source is not None and (references or connected.get("mcp_tools")):
            raise ProviderConnectionError("verified_review_unavailable")
        task = value(template, "task", "")
        if not isinstance(task, str):
            raise ProviderConnectionError("verified_review_unavailable")
        policy = GraphNodePolicy(
            model=value(template, "model"),
            effort=value(template, "effort"),
            task=task,
            task_from_input="task" in connected,
            timeout_seconds=value(template, "run_timeout_seconds", 180),
            skills=references,
        )
        if not policy.task_from_input and not task.strip():
            raise ProviderConnectionError("verified_review_unavailable")
        # The worker uses a virtual address and pipe; account identifiers and
        # their choice lists are not needed to execute this approved snapshot.
        data.pop("laomedo_authoring_bindings", None)
        if "provider_connection" in template:
            template["provider_connection"]["value"] = ""
            template["provider_connection"]["options"] = []
            template["provider_connection"].pop("options_metadata", None)
        return GraphRunNode(
            vertex_id=node["id"],
            provider=provider,
            connection_id=record.connection_id,
            generation=record.generation,
            review_source=review_source,
            policy=policy,
        )

    def _skill(self, node, connected):
        """Admit only an immutable imported reference, never sources or operations."""
        template = node["data"]["node"]["template"]
        if connected or any(
            self._value(template, field) not in (None, "", [])
            for field in (
                "source",
                "github_connection",
                "operation",
                "edit_request",
                "commit_id",
                "resolved_skill_id",
                "resolved_revision_id",
                "resolved_selection",
                "private_repository_id",
            )
        ):
            raise ProviderConnectionError("verified_review_unavailable")
        try:
            reference = SkillReference(
                skill_id=self._value(template, "skill_id"),
                revision_id=self._value(template, "revision_id"),
                tree_hash=self._value(template, "revision_id"),
            )
            binding = NodeResourceBindings.model_validate(
                node["data"].get("laomedo_authoring_bindings") or {}
            )
            if (
                binding.connection_id is not None
                or binding.generation is not None
                or (
                    binding.resources
                    and binding.resources
                    != [
                        ResourceBinding(
                            kind="skill",
                            id=reference.skill_id,
                            version=reference.revision_id,
                        )
                    ]
                )
            ):
                raise ProviderConnectionError("verified_review_unavailable")
            if self.skill_store is None or not self.skill_store.is_dir():
                raise ProviderConnectionError("skill_revision_unavailable")
            record = SkillStore(self.skill_store).revision(
                reference.skill_id, reference.revision_id
            )
            if record["tree_hash"] != reference.tree_hash:
                raise ProviderConnectionError("skill_revision_unavailable")
        except (SkillStoreError, OSError, ValidationError, KeyError, TypeError):
            raise ProviderConnectionError("skill_revision_unavailable") from None
        return reference

    def check_resources(self, graph):
        """Refuse output release from a deleted or corrupt pinned local revision."""
        for node in graph["nodes"]:
            if self.catalog.classification(node["data"]["type"]) == "LaomedoSkill":
                self._skill(node, {})

    @classmethod
    def mcp_selection(cls, node, connected, targets, *, require_target=True):
        """Admit a name-only, version-pinned registered Toolset selection."""
        template = node["data"]["node"]["template"]
        value = cls._value
        if (
            connected
            or (require_target and not targets)
            or set(template)
            - {
                "_type",
                "code",
                "mcp_server",
                "use_cache",
                "verify_ssl",
                "headers",
                "tool_execution_timeout",
                "tool",
                "tool_placeholder",
            }
            or node["data"]["node"].get("tool_mode") is not True
            or value(template, "verify_ssl", True) is not True
            or value(template, "use_cache", False) is not False
            or value(template, "tool_execution_timeout", 0) not in (None, 0)
            or any(
                value(template, field) not in (None, "", [], {})
                for field in ("headers", "tool", "tool_placeholder")
            )
        ):
            raise ProviderConnectionError("verified_review_unavailable")
        try:
            selected = value(template, "mcp_server")
            binding = NodeResourceBindings.model_validate(
                node["data"].get("laomedo_authoring_bindings") or {}
            )
            if (
                not isinstance(selected, dict)
                or set(selected) != {"name"}
                or binding.connection_id is not None
                or binding.generation is not None
                or len(binding.resources) != 1
            ):
                raise ProviderConnectionError("verified_review_unavailable")
            return GraphMcpSelection(
                vertex_id=node["id"],
                name=selected["name"],
                binding=binding.resources[0],
                targets=tuple(sorted(targets)),
            )
        except (ValidationError, ValueError, TypeError, KeyError):
            raise ProviderConnectionError("mcp_registration_unavailable") from None

    def _issue(self, node, connected):
        template = node["data"]["node"]["template"]
        if (
            connected
            or self._value(template, "public_service_only") is not True
            or any(
                self._value(template, field) not in (None, "", [])
                for field in ("operation", "issue_reference")
            )
        ):
            raise ProviderConnectionError("verified_review_unavailable")
        repository_url = self._value(template, "repository_url")
        repository_from_url(repository_url)
        choice = self._value(template, "issue_choice", "")
        match = (
            re.match(r"^#([1-9][0-9]*) ", choice) if isinstance(choice, str) else None
        )
        if match is None:
            raise ProviderConnectionError("verified_review_unavailable")
        return PublicIssueSelection(
            vertex_id=node["id"],
            repository_url=repository_url,
            number=int(match[1]),
            labels=tuple(labels_value(self._value(template, "labels", []))),
            state=self._value(template, "state", "open"),
        )

    def prepare(
        self, owner, lease_hash, flow_id, job_id, graph, *, timeout_seconds=600.0
    ):
        """Pin one graph; refuse unsupported paths before native account startup."""
        graph = GitHubNodeRunAdmission.executable_graph(
            self.catalog.effective_graph(graph)
        )
        nodes = {node["id"]: node for node in graph["nodes"]}
        if len(nodes) != len(graph["nodes"]) or not nodes:
            raise ProviderConnectionError("verified_review_unavailable")
        kinds = {
            key: self.catalog.classification(node["data"]["type"])
            for key, node in nodes.items()
        }
        connected = {key: {} for key in nodes}
        for edge in graph["edges"]:
            source, target = edge["source"], edge["target"]
            field = edge["data"]["targetHandle"]["fieldName"]
            output = edge["data"]["sourceHandle"]["name"]
            if (
                source not in nodes
                or target not in nodes
                or (field in connected[target] and field != "mcp_tools")
            ):
                raise ProviderConnectionError("verified_review_unavailable")
            if kinds[target] == "MCPTools" or (
                kinds[source] == "MCPTools"
                and (
                    kinds[target] not in self.AGENTS
                    or field != "mcp_tools"
                    or output != "component_as_tool"
                )
            ):
                raise ProviderConnectionError("verified_review_unavailable")
            if kinds[target] == "LaomedoSkill" or (
                kinds[source] == "LaomedoSkill"
                and (
                    kinds[target] not in self.AGENTS
                    or field != "skill_reference"
                    or output != "skill"
                )
            ):
                raise ProviderConnectionError("verified_review_unavailable")
            if kinds[target] in self.AGENTS:
                if (
                    field
                    not in {"task", "verified_changes", "skill_reference", "mcp_tools"}
                    or (field == "mcp_tools" and kinds[source] != "MCPTools")
                    or (
                        field == "skill_reference"
                        and (kinds[source] != "LaomedoSkill" or output != "skill")
                    )
                    or (
                        field == "verified_changes"
                        and (
                            kinds[target] != "LaomedoClaudeAgent"
                            or kinds[source] not in self.AGENTS
                            or output != "run"
                        )
                    )
                ):
                    raise ProviderConnectionError("verified_review_unavailable")
            if field == "mcp_tools":
                connected[target].setdefault(field, []).append(source)
            else:
                connected[target][field] = source
        selected, issues = [], []
        with self.connections._lock:
            self.connections.check_lease(lease_hash)
        # Registry verification does not hold the credential lifecycle lock.
        skills = {
            key: self._skill(nodes[key], connected[key])
            for key in nodes
            if kinds[key] == "LaomedoSkill"
        }
        mcps = tuple(
            self.mcp_selection(
                nodes[key],
                connected[key],
                [
                    target
                    for target in nodes
                    if key in connected[target].get("mcp_tools", [])
                ],
            )
            for key in nodes
            if kinds[key] == "MCPTools"
        )
        for target in nodes:
            bindings = [
                selection.binding.id
                for selection in mcps
                if target in selection.targets
            ]
            if len(bindings) != len(set(bindings)):
                raise ProviderConnectionError("mcp_duplicate_tool")
        # This initial executor requires every admitted Agent to complete.
        # Cycles/conditional scheduling cannot satisfy that closed contract.
        remaining = set(nodes)
        while remaining:
            ready = {
                key
                for key in remaining
                if not (
                    {
                        source
                        for value in connected[key].values()
                        for source in (value if isinstance(value, list) else [value])
                    }
                    & remaining
                )
            }
            if not ready:
                raise ProviderConnectionError("verified_review_unavailable")
            remaining -= ready
        with self.connections._lock:
            self.connections.check_lease(lease_hash)
            for key, node in nodes.items():
                kind = kinds[key]
                if kind in self.AGENTS:
                    selected.append(
                        self._node(
                            owner,
                            flow_id,
                            node,
                            self.AGENTS[kind],
                            connected[key].get("verified_changes"),
                            connected[key],
                            skills,
                        )
                    )
                elif kind == "LaomedoGitHubIssue":
                    issues.append(self._issue(node, connected[key]))
                elif kind == "LaomedoSkill":
                    for field in node["data"]["node"]["template"].values():
                        if isinstance(field, dict):
                            if "options" in field:
                                field["options"] = []
                            field.pop("options_metadata", None)
                elif kind == "MCPTools":
                    continue
                elif kind not in self.PLUMBING:
                    raise ProviderConnectionError("verified_review_unavailable")
                node["data"].pop("laomedo_authoring_bindings", None)
            digest = GitHubRunAuthority.digest_graph(graph)
            plan = GraphRunPlan(
                profile_id=owner,
                lease_hash=lease_hash,
                flow_id=flow_id,
                graph_digest="sha256:" + digest,
                nodes=tuple(selected),
                deadline=time.monotonic() + timeout_seconds,
            )
        removed = {selection.vertex_id for selection in mcps}
        graph["nodes"] = [node for node in graph["nodes"] if node["id"] not in removed]
        graph["edges"] = [
            edge for edge in graph["edges"] if edge["source"] not in removed
        ]
        if not graph["nodes"]:
            raise ProviderConnectionError("verified_review_unavailable")
        worker_digest = GitHubRunAuthority.digest_graph(graph)
        return PreparedProviderGraph(
            plan=plan,
            issues=tuple(issues),
            mcps=mcps,
            job=ProviderWorkerJob(
                job_id=job_id,
                flow_id=flow_id,
                graph=graph,
                graph_digest=worker_digest,
                catalog=GitHubCatalogSnapshot(
                    entries=tuple(
                        entry
                        for entry in self.catalog.snapshot.entries
                        if entry.classification != "MCPTools"
                    )
                ),
                timeout_seconds=timeout_seconds,
                providers=tuple(
                    ProviderNodeRoute(vertex_id=node.vertex_id, port=10000 + index)
                    for index, node in enumerate(selected)
                ),
                public_issues=tuple(issue.vertex_id for issue in issues),
            ),
        )

    def input_graph(self, graph, value, input_type):
        """Fold an approved text input into the effective graph before fingerprinting."""
        graph = self.catalog.effective_graph(graph)
        if value:
            selected = [
                node
                for node in graph["nodes"]
                if self.catalog.classification(node["data"]["type"]) == "TextInput"
            ]
            if input_type not in {"text", "any"} or not selected:
                raise ProviderConnectionError("verified_review_unavailable")
            for node in selected:
                node["data"]["node"]["template"]["input_value"]["value"] = value
        return graph
