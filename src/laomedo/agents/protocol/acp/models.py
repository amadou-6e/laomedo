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

    def tool_calls(self) -> list[dict]:
        """Project final observed ACP tool states without inventing native IDs."""
        calls = {}
        for update in self.updates:
            if update.get("sessionUpdate") not in {"tool_call", "tool_call_update"}:
                continue
            identity = update.get("toolCallId")
            if not isinstance(identity, str):
                continue
            calls.setdefault(identity, {}).update(update)
        return [
            {
                "call_id": identity,
                "tool": value.get("title"),
                "status": value.get("status"),
                "input": value.get("rawInput"),
                "output": value.get("rawOutput", value.get("content")),
                "error": value.get("status") == "failed",
            }
            for identity, value in calls.items()
        ]
