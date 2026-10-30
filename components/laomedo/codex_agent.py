"""Codex graph adapter; common lifecycle lives in the optional Langflow integration."""

from copy import deepcopy
from laomedo.integrations.langflow.agent.component import AgentComponent


class LaomedoCodexAgent(AgentComponent):
    display_name = "Laomedo Codex Agent"
    description = "Start, run, resume or cancel a Codex task with optional pinned skills through the local Docker runner."
    name = "LaomedoCodexAgent"
    provider_id = "codex"
    discover_models_on_upgrade = True
    supports_output_requirements = True
    supports_join_bridge = True
    bridge_url_env = "LAOMEDO_BRIDGE_URL"
    bridge_token_env = "LAOMEDO_BRIDGE_TOKEN_FILE"
    runner_token_env = "LAOMEDO_RUNNER_TOKEN_FILE"
    runner_token_default = "/run/secrets/laomedo-runner-token"

    def _validate_adapter(self):
        # A concrete adapter is a leaf. Old saved Claude/OpenCode code must
        # migrate its base before inheriting provider routing capabilities.
        if type(self) is not __class__:
            raise ValueError("agent_component_migration_required")

    inputs = [deepcopy(item) for item in AgentComponent.inputs]
    for _field in inputs:
        if _field.name == "runner_url":
            _field.value = "http://host.docker.internal:8765"
    del _field
