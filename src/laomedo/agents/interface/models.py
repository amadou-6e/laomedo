"""Typed requests inside host orchestration, with explicit component boundaries."""

from pydantic import BaseModel, ConfigDict, Field


class RunnerRequest(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    endpoint: str
    payload: dict | None = Field(repr=False)
    method: str

    @classmethod
    def from_component_request(cls, prepared):
        endpoint, payload, method = prepared
        return cls(endpoint=endpoint, payload=payload, method=method)

    def with_activity_attempt(self, invocation_id):
        return type(self)(
            endpoint=self.endpoint,
            payload={**self.payload, "activity_attempt_id": invocation_id},
            method=self.method,
        )

    def component_arguments(self):
        """Saved components retain their existing _http(endpoint, payload, method) API."""
        return self.endpoint, self.payload, self.method


# Closed external handoff/artifact vocabulary, not provider selection logic.
SUPPORTED_PROVIDERS = frozenset({"codex", "opencode", "claude"})
