"""Claude Code client with the shared Agent lifecycle and operation ports."""

from copy import deepcopy
import json
import os

from laomedo.codex_agent import LaomedoCodexAgent as Component
from lfx.io import StrInput


class LaomedoClaudeAgent(Component):
    display_name = "Laomedo Claude Agent"
    description = "Run pinned skills and validated operation proposals through Claude Code."
    name = "LaomedoClaudeAgent"
    activity_provider = "claude-code"
    inputs = [deepcopy(item) for item in Component.inputs if item.name not in
              {"model", "effort", "runner_url", "bridge_url", "handoff_reference"}] + [
        StrInput(name="model", display_name="Model", value="sonnet"),
        StrInput(name="effort", display_name="Reasoning Effort", value="low"),
        StrInput(name="runner_url", display_name="Runner URL", advanced=True,
                 value="http://host.docker.internal:8769"),
    ]

    def _prepare(self):
        if str(self.effort) not in {"low", "medium", "high"}:
            raise ValueError("unsupported_claude_effort")
        prior = getattr(self, "run_reference", None)
        prior = getattr(prior, "data", prior)
        if prior is None and getattr(self, "run_reference_json", ""):
            prior = json.loads(self.run_reference_json)
        if self.operation not in {"fresh", "start"} and isinstance(prior, dict) and prior.get("provider") != "claude":
            raise ValueError("run_provider_mismatch")
        return super()._prepare()

    def _token_file_path(self):
        return os.environ.get("LAOMEDO_CLAUDE_RUNNER_TOKEN_FILE",
                              "/run/secrets/laomedo-claude-runner-token")

    def _http(self, endpoint, payload, method):
        value = super()._http(endpoint, payload, method)
        if value.get("provider") != "claude":
            raise RuntimeError("runner_provider_mismatch")
        return value
