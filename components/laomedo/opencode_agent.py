"""OpenCode ports reuse the Codex client lifecycle; install the whole category."""

from copy import deepcopy
import json

from laomedo.codex_agent import LaomedoCodexAgent as Component
from lfx.io import StrInput


class LaomedoOpenCodeAgent(Component):
    display_name = "Laomedo OpenCode Agent"
    description = "Experimental private OpenCode adapter; isolated deployment remains required."
    name = "LaomedoOpenCodeAgent"
    inputs = [deepcopy(item) for item in Component.inputs if item.name not in
              {"model", "effort", "runner_url"}] + [
        StrInput(name="model", display_name="Provider/Model", required=True),
        StrInput(name="effort", display_name="Variant", value="default",
                 info="Only default is currently verified; other variants fail explicitly."),
        StrInput(name="runner_url", display_name="Runner URL", advanced=True,
                 value="http://host.docker.internal:8767"),
    ]

    def _prepare(self):
        if self.operation in {"fresh", "resume"} and str(self.effort) != "default":
            raise ValueError("unsupported_opencode_effort")
        prior = getattr(self, "run_reference", None)
        prior = getattr(prior, "data", prior)
        if prior is None and getattr(self, "run_reference_json", ""):
            prior = json.loads(self.run_reference_json)
        if self.operation != "fresh" and isinstance(prior, dict) and prior.get("provider") != "opencode":
            raise ValueError("run_provider_mismatch")
        return super()._prepare()

    def _http(self, endpoint, payload, method):
        value = super()._http(endpoint, payload, method)
        if value.get("provider") != "opencode":
            raise RuntimeError("runner_provider_mismatch")
        return value
