"""Pinned host-catalog validation before saved-account graph construction."""

from hashlib import sha256
import json

from laomedo.github.connections.errors import GitHubNodeAuthorizationError
from laomedo.integrations.langflow.authentication.models import (
    GitHubCatalogEntry,
    GitHubCatalogSnapshot,
)
from laomedo.integrations.langflow.authentication.settings import (
    GITHUB_GRAPH_COMPONENT_TYPES,
)


class GitHubGraphCatalog:
    """Validate exact classified sources without executing posted Python."""

    def __init__(self, snapshot: GitHubCatalogSnapshot):
        """Pin an immutable host snapshot; duplicate or unclassified entries refuse."""
        self.snapshot = snapshot
        self._codes = {}
        self._classifications = {}
        for entry in snapshot.entries:
            if (
                entry.classification not in GITHUB_GRAPH_COMPONENT_TYPES
                or entry.component_type in self._codes
            ):
                raise GitHubNodeAuthorizationError()
            self._codes[entry.component_type] = entry.code_digest
            self._classifications[entry.component_type] = entry.classification

    def classification(self, component_type):
        """Resolve only a canonical host-catalog identity, never a posted name."""
        try:
            return self._classifications[component_type]
        except (KeyError, TypeError):
            raise GitHubNodeAuthorizationError() from None

    @classmethod
    def capture(cls, registry):
        """Copy classified canonical source digests from an already trusted host catalog.

        The caller owns registry provenance. This must never receive a browser
        template dictionary or an untrusted worker's catalog response.
        """
        entries = {}
        try:
            for components in registry.values():
                for name, component in components.items():
                    classification = name
                    if classification not in GITHUB_GRAPH_COMPONENT_TYPES:
                        if not isinstance(name, str) or not name.startswith("ext:"):
                            continue
                        classification = component.get("name")
                        if classification not in GITHUB_GRAPH_COMPONENT_TYPES:
                            continue
                        if component.get("namespaced_id") != name:
                            raise GitHubNodeAuthorizationError()
                    code = component["template"]["code"]["value"]
                    if not isinstance(code, str) or not code:
                        raise GitHubNodeAuthorizationError()
                    digest = sha256(code.encode("utf-8")).hexdigest()
                    entry = GitHubCatalogEntry(
                        component_type=name,
                        classification=classification,
                        code_digest=digest,
                    )
                    if name in entries and entries[name] != entry:
                        raise GitHubNodeAuthorizationError()
                    entries[name] = entry
            return cls(
                GitHubCatalogSnapshot(
                    entries=tuple(entry for _, entry in sorted(entries.items()))
                )
            )
        except (AttributeError, KeyError, TypeError, ValueError):
            raise GitHubNodeAuthorizationError() from None

    def _validate(self, graph):
        """Check every leaf before expansion; grouped wrappers are never constructed."""
        try:
            nodes = graph["nodes"]
            if not isinstance(nodes, list) or not isinstance(graph["edges"], list):
                raise GitHubNodeAuthorizationError()
            for node in nodes:
                data = node["data"]
                component = data["node"]
                nested = component.get("flow")
                if nested:
                    self._validate(nested["data"])
                    continue
                kind = data["type"]
                code = component["template"]["code"]["value"]
                if (
                    kind not in self._codes
                    or not isinstance(code, str)
                    or sha256(code.encode("utf-8")).hexdigest() != self._codes[kind]
                ):
                    raise GitHubNodeAuthorizationError()
        except (AttributeError, KeyError, TypeError, ValueError):
            raise GitHubNodeAuthorizationError() from None

    def effective_graph(self, graph):
        """Return native-expanded JSON only after pre/post-expansion source checks.

        Apply execution tweaks before calling this method, and use its returned
        payload for both approval and worker construction. Native group proxies
        can override child inputs, so validating only pre-expansion code is unsafe.
        """
        from lfx.graph.graph.utils import process_flow

        try:
            payload = json.loads(json.dumps(graph, allow_nan=False))
            self._validate(payload)
            effective = process_flow(payload)
            self._validate(effective)
            if any(node["data"]["node"].get("flow") for node in effective["nodes"]):
                raise GitHubNodeAuthorizationError()
            return effective
        except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
            raise GitHubNodeAuthorizationError() from None
