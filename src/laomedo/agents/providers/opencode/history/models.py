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

    def tool_calls(self) -> list[dict]:
        """Project native tool names and final states, never human ACP titles."""
        calls = {}
        for message in self.messages:
            for part in message["parts"]:
                if part.get("type") != "tool" or not isinstance(
                    part.get("callID"), str
                ):
                    continue
                state = part.get("state")
                if not isinstance(state, dict):
                    continue
                calls[part["callID"]] = {
                    "call_id": part["callID"],
                    "tool": part.get("tool"),
                    "status": state.get("status"),
                    "input": state.get("input"),
                    "output": state.get("output"),
                    "error": state.get("error"),
                }
        return list(calls.values())


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

    def record_fields(self, baseline: "NativeHistory | None") -> dict:
        """Preserve the provider's public record fields from this attempt's native data."""
        messages = self.attempt_messages(self.root_id, baseline)
        recent = NativeExport(info=self.sessions[self.root_id].info, messages=messages)
        fields = {"tools": recent.tool_calls()}
        message = next(
            (
                message
                for message in reversed(messages)
                if message["info"].get("role") == "assistant"
            ),
            None,
        )
        if message is not None:
            terminal = message["info"]
            fields.update(native_turn_id=terminal["id"], usage=terminal.get("tokens"))
            fields["answer"] = (
                "\n".join(
                    part["text"]
                    for part in message["parts"]
                    if part.get("type") == "text" and isinstance(part.get("text"), str)
                )
                if not terminal.get("error")
                and terminal.get("time", {}).get("completed")
                else None
            )
            if terminal.get("providerID") and terminal.get("modelID"):
                fields["effective_model"] = (
                    terminal["providerID"] + "/" + terminal["modelID"]
                )
        return fields

    def attempt_sessions(self, baseline: "NativeHistory | None") -> set[str]:
        """Exclude unchanged historical children while retaining observed ancestry."""
        selected = {self.root_id}
        for identity in self.sessions:
            if not self.attempt_messages(identity, baseline):
                continue
            while identity not in selected:
                selected.add(identity)
                identity = self.sessions[identity].info.get("parentID")
                if identity not in self.sessions:
                    raise ValueError("Native history parent binding is incomplete")
        return selected

    def terminal_complete(self, baseline: "NativeHistory | None") -> bool:
        """Require terminal native assistant/tool receipts for newly observed work."""
        for identity in self.attempt_sessions(baseline):
            messages = self.attempt_messages(identity, baseline)
            if not messages and baseline and identity in baseline.sessions:
                continue  # This native ancestor had no new work in the attempt.
            assistant = [
                message
                for message in messages
                if message["info"].get("role") == "assistant"
            ]
            if (
                not assistant
                or type(assistant[-1]["info"].get("time", {}).get("completed"))
                is not int
            ):
                return False
            if any(
                call["status"] not in {"completed", "error"}
                for call in NativeExport(
                    info=self.sessions[identity].info, messages=messages
                ).tool_calls()
            ):
                return False
        return True
