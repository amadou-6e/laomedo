"""Canonical normalized PR values; effects remain gateway-owned."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, JsonValue
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


class PullRequestFeedbackContext(BaseModel):
    """New ticket snapshot; historical readers and grant checks stay unchanged."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    repository_url: str = Field(
        description="Existing admitted repository URL, preserving caller spelling."
    )
    labels: JsonValue = Field(
        description="Original selection labels; normalization belongs to execute, not this snapshot."
    )
    state: str = Field(description="Previously admitted selection state.")
    pr_number: int = Field(description="Previously admitted selected PR number.")
    expected: str = Field(
        description="Selected content digest already matched by the gateway."
    )
    pr: dict[str, JsonValue] = Field(
        description="Transport's existing PR snapshot, preserving optional provider extensions."
    )
    issued_monotonic: int | float = Field(
        description="Observed issuance marker in the mediator clock domain."
    )
    expires_monotonic: int | float = Field(
        description="Existing five-minute deadline in the same clock domain."
    )

    def to_payload(self) -> dict:
        """Write the existing ticket snapshot without strengthening old readers."""
        return self.model_dump()


class PRIdentity(BaseModel):
    """Minimal input identity; never a permission or authorization grant."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    repository: str = Field(description="Exact configured owner/repository identity.")
    number: int = Field(
        gt=0, description="Positive repository-local pull request number."
    )


class PRContextOutcome(BaseModel):
    """Evidence of an earlier operation, never an instruction to replay it."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    status: Literal["not_requested", "succeeded", "failed", "unknown"] = Field(
        description="Confirmed or uncertain earlier operation outcome."
    )
    error_category: str | None = Field(
        default=None, description="Earlier safe machine failure category, if present."
    )


class PRContextOperation(BaseModel):
    """An explicit normal-input request; host grants remain mandatory."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    action: Literal["modify", "close"] = Field(
        description="Requested narrow PR mutation."
    )
    request_id: str = Field(
        min_length=1,
        description="Stable idempotency identity supplied by the trusted caller.",
    )
    grant_ref: str = Field(
        min_length=1,
        description="Opaque existing host grant reference, never a provider token.",
    )
    changes: dict[str, JsonValue] | None = Field(
        default=None,
        description="Existing supplied title/body/labels patch; gateway validates permitted fields.",
    )


class PRContext(BaseModel):
    """One graph handoff containing PR identity/snapshot and request or outcome."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    schema_version: Literal["laomedo.github-pr.v1"] = Field(
        default="laomedo.github-pr.v1",
        description="Existing PR result envelope protocol.",
    )
    pr: GitHubPullRequest | PRIdentity | None = Field(
        default=None,
        description="Current PR snapshot or explicit minimal input identity.",
    )
    operation: PRContextOperation | PRContextOutcome | None = Field(
        default=None,
        description="Explicit requested mutation, or earlier operation evidence that must not replay.",
    )
    fetched_at: str | None = Field(
        default=None,
        description="Earlier fetch evidence; does not authorize or retarget execution.",
    )
    content_digest: str | None = Field(
        default=None,
        description="Earlier snapshot digest; execution always revalidates current state.",
    )
