"""Extract saved-account approval bounds from the effective native graph."""

import json
import re
from uuid import UUID

from laomedo.github.node_runs.errors import GitHubNodeAuthorizationError
from laomedo.github.node_runs.models import GitHubNodeSelection
from laomedo.github.contract import (
    GITHUB_CONNECTION_FIELD,
    HOST_CONNECTION,
    REPOSITORY_URL_FIELD,
    repository_from_url,
)
from laomedo.github.issues.contract import ISSUE_CHOICE_FIELD, ISSUE_OPERATION_FIELD
from laomedo.github.pull_requests.contract import PR_CHOICE_FIELD, PR_CONTEXT_FIELD
from laomedo.github.pull_requests.context import context_value
from laomedo.github.pull_requests.models import PRContextOperation


class GitHubNodeRunAdmission:
    """Native graph projection; browser target lists are never authority."""

    # Canonical classification -> (selection kind, target picker, operation input).
    NODE_FIELDS = {
        "LaomedoGitHubIssue": ("issue", ISSUE_CHOICE_FIELD, ISSUE_OPERATION_FIELD),
        "LaomedoGitHubPR": ("pr", PR_CHOICE_FIELD, PR_CONTEXT_FIELD),
    }

    def __init__(self, authority, catalog):
        """Use the broker's run authority and the run's pinned host catalog."""
        self.authority = authority
        self.catalog = catalog

    def effective_graph(self, graph):
        """Pin source and native group expansion before deriving any authority."""
        return self.executable_graph(self.catalog.effective_graph(graph))

    @staticmethod
    def executable_graph(graph):
        """Discard known canvas-only geometry without dropping executable fields."""
        if not isinstance(graph, dict):
            raise GitHubNodeAuthorizationError()
        try:
            graph = json.loads(json.dumps(graph, allow_nan=False))
        except (TypeError, ValueError):
            raise GitHubNodeAuthorizationError() from None
        if not isinstance(graph.get("nodes"), list) or not isinstance(
            graph.get("edges"), list
        ):
            raise GitHubNodeAuthorizationError()
        graph.pop("viewport", None)
        for node in graph.get("nodes", []):
            if not isinstance(node, dict):
                raise GitHubNodeAuthorizationError()
            for name in (
                "position",
                "positionAbsolute",
                "selected",
                "dragging",
                "width",
                "height",
                "measured",
                "resizing",
                "zIndex",
            ):
                node.pop(name, None)
        for edge in graph.get("edges", []):
            if not isinstance(edge, dict):
                raise GitHubNodeAuthorizationError()
            edge.pop("selected", None)
        return graph

    async def prepare(self, scope, flow_id, graph):
        """Derive approval bounds from host-admitted effective node parameters."""
        graph = self.effective_graph(graph)
        selections = []
        try:
            nodes, edges = graph["nodes"], graph["edges"]
            if not isinstance(nodes, list) or not isinstance(edges, list):
                raise GitHubNodeAuthorizationError()
            for node in nodes:
                data = node.get("data", {})
                kind = self.catalog.classification(data.get("type"))
                if kind not in self.NODE_FIELDS:
                    continue
                resource, choice_field, operation_field = self.NODE_FIELDS[kind]
                template = data["node"]["template"]
                connection = template.get(GITHUB_CONNECTION_FIELD, {}).get("value", "")
                if connection == HOST_CONNECTION:
                    continue
                if (
                    data.get("tool_mode")
                    or data.get("node", {}).get("tool_mode")
                    or node.get("tool_mode")
                ):
                    raise GitHubNodeAuthorizationError()
                connection_id = UUID(connection)
                repository = repository_from_url(
                    template[REPOSITORY_URL_FIELD]["value"]
                )
                selected = self.authority.connections.selected_repository(
                    scope.owner_id, connection_id, repository
                )
                if selected is None:
                    raise GitHubNodeAuthorizationError()
                choice = template.get(choice_field, {}).get("value", "")
                match = (
                    re.match(r"^#([1-9][0-9]*) ", choice)
                    if isinstance(choice, str)
                    else None
                )
                operations = ()
                static_operation = template.get(operation_field, {}).get("value")
                if static_operation:
                    if resource == "issue":
                        action = (
                            static_operation.get("action")
                            if isinstance(static_operation, dict)
                            else None
                        )
                        operations = (
                            (action,)
                            if action in {"modify", "close"}
                            else ("modify", "close")
                        )
                    else:
                        context = context_value(static_operation)
                        if isinstance(context.operation, PRContextOperation):
                            operations = (context.operation.action,)
                for edge in edges:
                    if edge.get("target") != node["id"]:
                        continue
                    handle = edge["data"]["targetHandle"]
                    if (
                        isinstance(handle, dict)
                        and handle.get("fieldName") == operation_field
                    ):
                        operations = ("modify", "close")
                selections.append(
                    GitHubNodeSelection(
                        vertex_id=node["id"],
                        kind=resource,
                        connection_id=connection_id,
                        repository=selected,
                        number=int(match[1]) if match else None,
                        operations=operations,
                    )
                )
        except (KeyError, TypeError, ValueError, AttributeError):
            raise GitHubNodeAuthorizationError() from None
        if not selections:
            return None
        return await self.authority.prepare(scope, flow_id, graph, selections)
