"""Private result joining a verified image to its Docker CLI environment."""

from pydantic import BaseModel, ConfigDict, Field


class DockerSelection(BaseModel):
    """Keep SDK preflight and subsequent native launch on the selected daemon."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    image_id: str = Field(description="Verified immutable local Codex image ID.")
    environment: dict[str, str] = Field(
        exclude=True,
        repr=False,
        description="Private host environment snapshot with the resolved Docker endpoint pinned.",
    )
