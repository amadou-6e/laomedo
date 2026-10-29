"""Results derived from observed ACP updates and terminal prompt responses."""

from pydantic import BaseModel, Field


class AcpTurn(BaseModel):
    """One terminal prompt outcome; interruption never implies successful work."""

    session_id: str = Field(description="Agent's native persisted session identity.")
    stop_reason: str = Field(description="Unmodified ACP terminal stop reason.")
    answer: str = Field(description="Ordered text from this prompt's agent messages.")
    updates: list[dict] = Field(
        description="Observed ACP updates for this prompt only."
    )
    usage: dict | None = Field(
        default=None,
        description="Native ACP usage when supplied; absent means unknown.",
    )
