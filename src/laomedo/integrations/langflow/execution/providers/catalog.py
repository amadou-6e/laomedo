"""Build the provider broker's small catalog from explicit operator-installed code."""

from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

from laomedo.integrations.langflow.assistant.catalog import ComponentCatalog
from laomedo.integrations.langflow.graph_admission.catalog import GitHubGraphCatalog
from laomedo.integrations.langflow.execution.worker.errors import GraphWorkerError


class ProviderComponentCatalog:
    """One startup-only catalog; no posted code or component hooks enter the host."""

    FILES = (
        ("codex_agent.py", "LaomedoCodexAgent"),
        ("claude_agent.py", "LaomedoClaudeAgent"),
        ("opencode_agent.py", "LaomedoOpenCodeAgent"),
        ("github_issue.py", "LaomedoGitHubIssue"),
    )

    def __init__(self, components_root: Path):
        from lfx.components.input_output.text import TextInputComponent
        from lfx.components.input_output.text_output import TextOutputComponent
        from lfx.components.models_and_agents.prompt import PromptComponent

        registry = {"input_output": {}, "laomedo": {}}
        for component in (TextInputComponent, TextOutputComponent, PromptComponent):
            node = component().to_frontend_node()
            registry["input_output"][node["data"]["type"]] = node["data"]["node"]
        for filename, name in self.FILES:
            path = components_root / "laomedo" / filename
            if not path.is_file() or path.is_symlink():
                raise GraphWorkerError()
            module_name = "laomedo_provider_catalog_" + name
            spec = spec_from_file_location(module_name, path)
            module = module_from_spec(spec)
            sys.modules[module_name] = module
            try:
                spec.loader.exec_module(module)
                node = getattr(module, name)().to_frontend_node()
            finally:
                sys.modules.pop(module_name, None)
            if node["data"]["type"] != name:
                raise GraphWorkerError()
            registry["laomedo"][name] = node["data"]["node"]
        self._registry = registry
        self.admission = GitHubGraphCatalog.capture(registry)

    async def for_owner(self, owner):
        """Project installed policy-filtered templates without dynamic discovery."""
        from lfx.utils.component_aliases import build_component_identity_index
        from langflow.api.v1.endpoints import (
            _filter_component_palette_by_catalog_policy,
            _filter_component_palette_by_provider_policy,
        )
        from langflow.services.deps import get_catalog_policy_service

        snapshot = deepcopy(self._registry)
        snapshot = _filter_component_palette_by_catalog_policy(
            snapshot,
            blocked_component_keys=get_catalog_policy_service().snapshot.blocked_component_keys,
            component_identity_index=build_component_identity_index(snapshot),
        )
        return ComponentCatalog(
            await _filter_component_palette_by_provider_policy(snapshot, user_id=owner)
        )
