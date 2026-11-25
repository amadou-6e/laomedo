"""Models for explicit selected-account pull request reads."""

from typing import Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from laomedo.github.connections.models import GitHubReadAuthorization


class PrivatePullRequestSelection(BaseModel):
    """Select one consented repository; the owner is authenticated separately."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    connection_id: UUID
    repository_id: int = Field(strict=True, gt=0)


class PrivatePullRequestRead(PrivatePullRequestSelection):
    """Select a positive PR number within the admitted repository."""

    pr_number: int = Field(strict=True, gt=0, le=2**53 - 1)


class PrivatePullRequestResult(BaseModel):
    """Bind a buffered response to the authority needed to release it."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    authorization: GitHubReadAuthorization
    payload: dict[str, Any]
