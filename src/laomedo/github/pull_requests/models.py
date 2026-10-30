"""Canonical normalized PR values; effects remain gateway-owned."""

from pydantic import BaseModel, ConfigDict, Field
from laomedo.github.issues.models import GitHubIssue


class PullRequestHead(BaseModel):
    """Group the exact source branch and commit, including a deleted fork."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    repository: str | None = Field(
        description="Source owner/repository, or null for a deleted fork."
    )
    branch: str = Field(description="Source branch name, preserving provider spelling.")
    sha: str = Field(
        pattern=r"^[0-9a-f]{40}$",
        description="Validated immutable forty-character Git commit hash.",
    )


class GitHubPullRequest(GitHubIssue):
    """Reuse issue-shaped fields, without treating this PR as an issue operation.

    This is value-schema inheritance only. Callers select issue/PR operations
    explicitly; isinstance checks must never authorize or route a GitHub effect.
    """

    draft: bool = Field(description="Whether GitHub currently marks the PR as a draft.")
    merged: bool = Field(description="Whether the provider supplied a merge timestamp.")
    head: PullRequestHead = Field(
        description="Source repository, branch and immutable commit."
    )
    base: str = Field(description="Admitted target branch in this repository.")

    def to_payload(self) -> dict:
        """Preserve the historical PR field order as well as its values and nulls."""
        value = self.model_dump()
        return {
            key: value[key]
            for key in (
                "repository",
                "number",
                "url",
                "node_id",
                "title",
                "body",
                "labels",
                "state",
                "draft",
                "merged",
                "updated_at",
                "head",
                "base",
            )
        }
