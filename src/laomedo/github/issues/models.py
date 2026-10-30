"""Canonical issue values after the public response checks have succeeded."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class GitHubIssue(BaseModel):
    """Normalized issue state; its identity never confers write authority."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)
    repository: str = Field(description="Admitted owner/repository identity.")
    number: int = Field(gt=0, description="Positive repository-local issue or PR number.")
    url: str = Field(description="Public issue or PR URL, admitted by the response boundary.")
    node_id: str = Field(description="Opaque GitHub node identity.")
    title: str = Field(description="Current title, preserving provider text.")
    body: str = Field(description="Current body; an absent provider body is empty.")
    labels: list[str] = Field(description="Validated, sorted, unique label names.")
    state: Literal["open", "closed"] = Field(description="Observed GitHub item state.")
    updated_at: str = Field(description="Provider update stamp, preserved verbatim.")

    def to_payload(self) -> dict:
        """Return the existing nine-field public record without adding defaults."""
        return self.model_dump()
