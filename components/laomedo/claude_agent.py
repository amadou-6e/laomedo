"""Claude Code client with the shared Agent lifecycle and operation ports."""

from copy import deepcopy
import json
import os

from laomedo.codex_agent import LaomedoCodexAgent as Component
from laomedo.claude_models import EFFORTS


class LaomedoClaudeAgent(Component):
    display_name = "Laomedo Claude Agent"
    description = "Run pinned skills and validated operation proposals through Claude Code."
    name = "LaomedoClaudeAgent"
    activity_provider = "claude-code"
    inputs = [deepcopy(item) for item in Component.inputs if item.name not in
              {"bridge_url", "handoff_reference"}]
    for _field in inputs:
        if _field.name == 'model':
            _field.value = 'sonnet'
            _field.options = []
            _field.info = ('Refresh the configured Claude runner for the model picker from '
                           'your signed-in Claude Code account. No prompt or model turn is sent.')
        elif _field.name == 'effort':
            _field.value = 'low'
            _field.options = []
            _field.info = ('Supported effort levels for the selected Claude model. '
                           'Default omits the effort override for models without this control.')
        elif _field.name == 'runner_url':
            _field.value = 'http://host.docker.internal:8769'
    del _field

    def _prepare(self):
        if str(self.effort) not in EFFORTS:
            raise ValueError("unsupported_claude_effort")
        prior = getattr(self, "run_reference", None)
        prior = getattr(prior, "data", prior)
        if prior is None and getattr(self, "run_reference_json", ""):
            prior = json.loads(self.run_reference_json)
        if self.operation not in {"fresh", "start"} and isinstance(prior, dict) and prior.get("provider") != "claude":
            raise ValueError("run_provider_mismatch")
        return super()._prepare()

    def _token_file_path(self):
        return self._runner_token_file_path()

    def _runner_token_file_path(self):
        return os.environ.get("LAOMEDO_CLAUDE_RUNNER_TOKEN_FILE",
                              "/run/secrets/laomedo-claude-runner-token")

    def _http(self, endpoint, payload, method):
        value = super()._http(endpoint, payload, method)
        if value.get("provider") != "claude":
            raise RuntimeError("runner_provider_mismatch")
        return value
