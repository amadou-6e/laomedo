"""Host-generated PR creation values, distinct from authorization and effects."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class PullRequestPublicationRequest(BaseModel):
    """Admitted draft-PR creation proposal before a PR identity exists."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    head: str = Field(description="Host-authorized source branch.")
    base: str = Field(description="Host-authorized target branch.")
    title: str = Field(description="Existing admitted PR title.")
    body: str = Field(
        description="Existing admitted body including its host correlation marker."
    )
    marker: str = Field(
        description="Host-generated reconciliation marker, never model authority."
    )
    draft: Literal[True] = Field(
        default=True, description="Publication creates a draft PR for separate review."
    )

    def to_payload(self) -> dict:
        """Preserve the six-field private publication journal request."""
        return self.model_dump()
