"""OpenCode graph adapter over the provider-neutral Agent lifecycle."""

from copy import deepcopy
import json
import os

from laomedo.integrations.langflow.agent.component import AgentComponent as Component
from lfx.io import DropdownInput; from lfx.io import StrInput


class LaomedoOpenCodeAgent(Component):
    display_name = "Laomedo OpenCode Agent"
    description = "Run pinned skills with OpenCode through its isolated local Docker runner."
    name = "LaomedoOpenCodeAgent"
    provider_id = "opencode"
    activity_provider = "opencode"
    inputs = [deepcopy(item) for item in Component.inputs if item.name not in
              {"model", "effort", "runner_url", "bridge_url", "output_requirements",
               "output_requirements_json", "output_retries"}] + [
        DropdownInput(name="model", display_name="Provider/Model", required=True, value="",
                      options=[], combobox=False, real_time_refresh=True, refresh_button=True,
                      info="Refresh to load models from connected OpenCode providers on the configured runner."),
        DropdownInput(name="effort", display_name="Variant", value="default",
                      options=["default"], combobox=False,
                 info="Only default is currently verified; other variants fail explicitly."),
        StrInput(name="runner_url", display_name="Runner URL", advanced=True,
                 value="http://host.docker.internal:8768", real_time_refresh=True),
    ]

    # Keep the shared Agent layout: task/operation, model/variant, skill port,
    # then node-owned advanced settings. Hidden compatibility fields stay hidden.
    inputs.sort(key=lambda item: next((index for index, field in enumerate(Component.inputs)
                                      if field.name == item.name), len(Component.inputs)))

    async def update_build_config(self, build_config, field_value, field_name=None):
        return await self._update_model_config(build_config, field_value, field_name)

    async def update_frontend_node(self, new_frontend_node, current_frontend_node):
        # Loading/upgrading a graph must not start a credentialed controller.
        # Discovery is explicit through the model dropdown's Refresh action.
        updated = await super().update_frontend_node(new_frontend_node, current_frontend_node)
        previous = current_frontend_node.get("template", {})
        for name in ("model", "effort"):
            field = updated["template"].get(name, {})
            choices = previous.get(name, {}).get("options", [])
            choices = [value for value in choices if isinstance(value, str) and value]
            value = field.get("value")
            if isinstance(value, str) and value and value not in choices:
                choices.append(value)
            field["options"] = choices
        return updated

    def _prepare(self):
        if self.operation in {"fresh", "start", "resume"} and str(self.effort) != "default":
            raise ValueError("unsupported_opencode_effort")
        prior = getattr(self, "run_reference", None)
        prior = getattr(prior, "data", prior)
        if prior in (None, "", []) and getattr(self, "run_reference_json", ""):
            prior = json.loads(self.run_reference_json)
        if self.operation not in {"fresh", "start"} and isinstance(prior, dict) and prior.get("provider") != "opencode":
            raise ValueError("run_provider_mismatch")
        return super()._prepare()

    def _model_catalog_token_file_path(self):
        return self._token_file_path()

    def _token_file_path(self):
        return self._runner_token_file_path()

    def _runner_token_file_path(self):
        return os.environ.get("LAOMEDO_OPENCODE_RUNNER_TOKEN_FILE",
                              "/run/secrets/laomedo-opencode-runner-token")

    def _http(self, endpoint, payload, method):
        value = super()._http(endpoint, payload, method)
        if value.get("provider") != "opencode":
            raise RuntimeError("runner_provider_mismatch")
        return value
