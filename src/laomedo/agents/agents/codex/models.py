"""Codex-owned continuation bindings, separate from successful output artifacts."""

from pydantic import BaseModel, ConfigDict, Field


class ResumeCheckpoint(BaseModel):
    """Bind a settled interrupted attempt to its existing session and frozen files."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    attempt_id: str = Field(
        description="Exact settled Activity attempt that owns these facts."
    )
    thread_id: str = Field(
        description="Existing native session; no fresh-session substitution."
    )
    workspace_hash: str = Field(
        pattern=r"^sha256:[0-9a-f]{64}$",
        description="Verified retained workspace digest after owned resources settled.",
    )
    runner_instance_id: str = Field(
        description="Only this still-running host can admit continuation."
    )
