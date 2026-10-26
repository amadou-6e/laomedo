"""Claude Code client with the shared Agent lifecycle and operation ports."""

from copy import deepcopy
import json
import os

from laomedo.codex_agent import LaomedoCodexAgent as Component
from laomedo.claude_models import EFFORTS
from langflow.io import IntInput


class LaomedoClaudeAgent(Component):
    display_name = "Laomedo Claude Agent"
    description = "Run Claude Code in an isolated container with optional pinned skills and validated operations."
    name = "LaomedoClaudeAgent"
    activity_provider = "claude-code"
    inputs = [deepcopy(item) for item in Component.inputs]
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
    inputs.append(IntInput(name='run_timeout_seconds', display_name='Execution Timeout',
                           value=180, advanced=True,
                           info='Total execution deadline in seconds, including output corrections. HTTP Timeout controls only how long the graph waits.'))

    def _prepare(self):
        if str(self.effort) not in EFFORTS:
            raise ValueError("unsupported_claude_effort")
        prior = getattr(self, "run_reference", None)
        prior = getattr(prior, "data", prior)
        if prior in (None, '', []) and getattr(self, "run_reference_json", ""):
            prior = json.loads(self.run_reference_json)
        if self.operation not in {"fresh", "start"} and isinstance(prior, dict) and prior.get("provider") != "claude":
            raise ValueError("run_provider_mismatch")
        endpoint, payload, method = super()._prepare()
        if self.operation in {'fresh', 'start', 'resume'}:
            timeout = getattr(self, 'run_timeout_seconds', 180)
            if type(timeout) is not int or not 1 <= timeout <= 86400:
                raise ValueError('claude_turn_timeout_invalid')
            payload.get('runner_body', payload)['run_timeout_seconds'] = timeout
        return endpoint, payload, method

    def _token_file_path(self):
        return super()._token_file_path()

    def _runner_token_file_path(self):
        return os.environ.get("LAOMEDO_CLAUDE_RUNNER_TOKEN_FILE",
                              "/run/secrets/laomedo-claude-runner-token")

    def _http(self, endpoint, payload, method):
        value = super()._http(endpoint, payload, method)
        if value.get("provider") != "claude":
            raise RuntimeError("runner_provider_mismatch")
        return value
