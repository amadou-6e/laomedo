"""Shared authenticated intent values; gateways own effects and admission."""

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class GitHubGrantBinding(BaseModel):
    """Safe grant/run identities already authenticated by the host gateway."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    grant_id: str = Field(
        description="Previously authenticated host grant identity, never its token."
    )
    run_id: str = Field(
        description="Run identity matched against the authenticated grant."
    )


class GitHubOperationIntent(BaseModel):
    """Canonical issue/PR operation identity before any remote effect."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    repository: str = Field(description="Admitted owner/repository identity.")
    number: int = Field(
        description="Previously admitted repository-local issue or PR number."
    )
    labels: list[str] = Field(
        description="Existing normalized selection labels in unchanged order."
    )
    state: str = Field(description="Previously admitted selection state.")
    operation: dict[str, JsonValue] = Field(
        description="Existing JSON-admitted close/modify request, retaining optional changes."
    )
    binding: GitHubGrantBinding = Field(
        description="Authenticated grant/run identities without credential material."
    )

    def to_payload(self) -> dict:
        """Preserve all six exact hash inputs, including the admitted operation."""
        return self.model_dump()
