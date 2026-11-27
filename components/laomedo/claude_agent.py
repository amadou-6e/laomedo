"""Claude Code client with the shared Agent lifecycle and operation ports."""

from copy import deepcopy
import json

from laomedo.integrations.langflow.agent.component import AgentComponent as Component
from laomedo.agents.agents.claude.settings import EFFORTS
from laomedo.agents.interface.langflow.errors import RunnerRequestError
from laomedo.integrations.langflow.provider_connections.bindings import (
    ProviderGraphBindings,
)
from lfx.io import DataInput, IntInput


class LaomedoClaudeAgent(Component):
    display_name = "Laomedo Claude Agent"
    description = "Run Claude Code in an isolated container with optional pinned skills, selected MCP tools and validated operations."
    name = "LaomedoClaudeAgent"
    provider_id = "claude"
    activity_provider = "claude-code"
    discover_models_on_upgrade = True
    supports_output_requirements = True
    supports_join_bridge = True
    present_native_models = True
    catalog_timeout_seconds = 75
    catalog_provider = "claude"
    runner_token_env = "LAOMEDO_CLAUDE_RUNNER_TOKEN_FILE"
    runner_token_default = "/run/secrets/laomedo-claude-runner-token"
    bridge_url_env = "LAOMEDO_CLAUDE_BRIDGE_URL"
    bridge_token_env = "LAOMEDO_CLAUDE_BRIDGE_TOKEN_FILE"
    inputs = [
        deepcopy(item) for item in Component.inputs if item.name != "handoff_reference"
    ]
    for _field in inputs:
        if _field.name == "model":
            _field.value = "sonnet"
            _field.options = []
            _field.info = (
                "Refresh the configured Claude runner for the model picker from "
                "your signed-in Claude Code account. No prompt or model turn is sent."
            )
        elif _field.name == "effort":
            _field.value = "low"
            _field.options = []
            _field.info = (
                "Supported effort levels for the selected Claude model. "
                "Default omits the effort override for models without this control."
            )
        elif _field.name == "runner_url":
            _field.value = "http://host.docker.internal:8769"
    del _field
    inputs.insert(
        next(index for index, field in enumerate(inputs) if field.name == "mcp_tools")
        + 1,
        DataInput(
            name="verified_changes",
            display_name="Verified Changes",
            info="Connect the Run Reference of a completed agent that made workspace edits.",
        ),
    )
    inputs.append(
        IntInput(
            name="run_timeout_seconds",
            display_name="Execution Timeout",
            value=180,
            advanced=True,
            info="Total execution deadline in seconds, including output corrections. HTTP Timeout controls only how long the graph waits.",
        )
    )

    def _prepare(self):
        self._verified_review_grant = None
        self._verified_expected_request_hash = None
        verified = getattr(self, "verified_changes", None)
        verified = getattr(verified, "data", verified)
        if verified not in (None, "", []):
            if (
                self.operation not in {"fresh", "start"}
                or not isinstance(verified, dict)
                or not isinstance(verified.get("run_id"), str)
                or getattr(self, "run_reference", None) not in (None, "", [])
                or getattr(self, "run_reference_json", "")
                or getattr(self, "skill_reference", None) not in (None, "", [])
                or getattr(self, "mcp_tools", None) not in (None, "", [])
                or self._bridge_base()
            ):
                raise ValueError("verified_review_unavailable")
        if str(self.effort) not in EFFORTS:
            raise ValueError("unsupported_claude_effort")
        prior = getattr(self, "run_reference", None)
        prior = getattr(prior, "data", prior)
        if prior in (None, "", []) and getattr(self, "run_reference_json", ""):
            prior = json.loads(self.run_reference_json)
        if (
            self.operation not in {"fresh", "start"}
            and isinstance(prior, dict)
            and prior.get("provider") != "claude"
        ):
            raise ValueError("run_provider_mismatch")
        endpoint, payload, method = super()._prepare()
        if self.operation in {"fresh", "start", "resume"}:
            timeout = getattr(self, "run_timeout_seconds", 180)
            if type(timeout) is not int or not 1 <= timeout <= 86400:
                raise ValueError("claude_turn_timeout_invalid")
            payload.get("runner_body", payload)["run_timeout_seconds"] = timeout
        if verified not in (None, "", []):
            if set(payload) - {
                "request_id",
                "task",
                "model",
                "effort",
                "skill_refs",
                "run_timeout_seconds",
            }:
                raise ValueError("verified_review_unavailable")
            channel = self._isolated_channel()
            if channel is not None:
                self._verified_expected_request_hash = channel.review(
                    self._vertex.id, payload
                )
            else:
                self._verified_review_grant, self._verified_expected_request_hash = (
                    ProviderGraphBindings.stage_review(
                        self, verified["run_id"], payload
                    )
                )
        return endpoint, payload, method

    def _request_headers(self, endpoint, method):
        """Send a staged grant only to its saved runner's async start route."""
        grant = getattr(self, "_verified_review_grant", None)
        saved = getattr(self, "_saved_endpoint", None)
        if (
            grant
            and saved
            and method == "POST"
            and endpoint == saved[0] + "/v1/runs/async"
        ):
            return {"X-Laomedo-Verified-Review": grant}
        return {}

    def _token_file_path(self):
        return super()._token_file_path()

    def _runner_token_file_path(self):
        return super()._runner_token_file_path()

    def _http(self, endpoint, payload, method):
        try:
            value = super()._http(endpoint, payload, method)
        except RunnerRequestError as failure:
            pinned = getattr(self, "_saved_endpoint", None)
            if not (
                ProviderGraphBindings.service is not None
                and pinned is not None
                and method == "POST"
                and self.operation in {"fresh", "start"}
                and failure.code
                == "runner_model_catalog_unavailable_check_runner_connection"
                and failure.diagnostics.get("http_status") == 400
                and failure.diagnostics.get("runner_code") == failure.code
                and not getattr(self, "_verified_review_grant", None)
            ):
                raise
            self._model_catalog({}, saved_endpoint=pinned)
            value = super()._http(endpoint, payload, method)
        if value.get("provider") != "claude":
            raise RuntimeError("runner_provider_mismatch")
        return value
