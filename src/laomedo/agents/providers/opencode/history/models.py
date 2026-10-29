"""Opaque native exports with explicit identity and attempt-boundary validation."""

from pathlib import Path
import re
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class HistorySource(BaseModel):
    """Host-owned bindings; no credential or graph-supplied command is accepted."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    store: Path = Field(
        description="Dedicated native session-store directory, excluding the credential file."
    )
    image_id: str = Field(
        pattern=r"^sha256:[0-9a-f]{64}$",
        description="Verified immutable OpenCode controller image used only for native export.",
    )
    endpoint: str = Field(
        description="Original resolved local Docker endpoint for owned metadata jobs."
    )
    receipts: Path = Field(
        description="Private durable receipt directory recovered before another dispatch."
    )


class NativeExport(BaseModel):
    """Original CLI export shape; native fields stay intact at this boundary."""

    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)
    info: dict = Field(
        description="Unmodified native session metadata, including ID and explicit parent relationship."
    )
    messages: list[dict] = Field(
        description="Unmodified native message and part payloads, including per-message counters."
    )

    def bind(self, session_id: str, parent: str | None) -> None:
        """Reject mismatched native identities before retaining or projecting data."""
        if self.info.get("id") != session_id or self.info.get("parentID") != parent:
            raise ValueError("Native export session binding mismatch")
        identities = set()
        for message in self.messages:
            info = message.get("info", {})
            if (
                not isinstance(info, dict)
                or info.get("sessionID") != session_id
                or not isinstance(info.get("id"), str)
                or info["id"] in identities
                or not isinstance(message.get("parts"), list)
            ):
                raise ValueError("Native export message binding mismatch")
            identities.add(info["id"])
            for part in message["parts"]:
                if (
                    not isinstance(part, dict)
                    or part.get("sessionID", session_id) != session_id
                    or part.get("messageID", info["id"]) != info["id"]
                ):
                    raise ValueError("Native export part binding mismatch")

    def message_ids(self) -> set[str]:
        """Return native message identities for an exact resume baseline."""
        return {message["info"]["id"] for message in self.messages}

    def child_ids(self) -> set[str]:
        """Follow only native task metadata attesting this exact parent session."""
        children = set()
        for message in self.messages:
            for part in message["parts"]:
                if part.get("type") != "tool" or part.get("tool") != "task":
                    continue
                state = part.get("state")
                metadata = state.get("metadata") if isinstance(state, dict) else None
                if (
                    not isinstance(metadata, dict)
                    or metadata.get("parentSessionId") != self.info["id"]
                ):
                    continue
                child = metadata.get("sessionId")
                if isinstance(child, str) and re.fullmatch(r"ses_[A-Za-z0-9]+", child):
                    children.add(child)
        return children


class NativeHistory(BaseModel):
    """One verified parent-linked export batch from a consistent store snapshot."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    root_id: str = Field(
        description="Actual native session accepted for this runner attempt."
    )
    captured_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Host receipt time of the consistent source snapshot, separate from native message times.",
    )
    sessions: dict[str, NativeExport] = Field(
        default_factory=dict,
        description="Exports keyed by independently verified native session identity.",
    )

    def attempt_messages(
        self, session_id: str, baseline: "NativeHistory | None"
    ) -> list[dict]:
        """Attribute new native message identities only; never sum repeated snapshots."""
        earlier = baseline.sessions.get(session_id) if baseline else None
        if baseline and session_id != self.root_id and earlier is None:
            root_messages = self.attempt_messages(self.root_id, baseline)
            starts = [
                message["info"].get("time", {}).get("created")
                for message in root_messages
                if message["info"].get("role") == "user"
            ]
            created = self.sessions[session_id].info.get("time", {}).get("created")
            if (
                not starts
                or any(type(value) is not int for value in starts)
                or type(created) is not int
                or created < min(starts)
            ):
                raise ValueError("Native child usage baseline is unknown")
        ids = earlier.message_ids() if earlier else set()
        return [
            message
            for message in self.sessions[session_id].messages
            if message["info"]["id"] not in ids
        ]
