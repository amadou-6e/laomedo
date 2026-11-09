"""Codex native observations; successful tool evidence is retained for context."""

import json
import re

from session_retro.models import NormalizedEvent, SourceRecord
from session_retro.redaction import Redactor
from session_retro.settings import Settings


class CodexEventDecoder:
    """Normalize bounded source records without trusting embedded instructions.

    Parameters
    ----------
    settings : Settings
        Resource bounds and extraction limits.

    Notes
    -----
    Keeps the latest observed turn identity; no I/O or content execution.
    """

    def __init__(self, settings: Settings):
        """Retain injected limits and current observed turn identity."""
        self.settings = settings
        self.redactor = Redactor()
        self.turn_id = None

    def decode(
        self, record: SourceRecord, *, full_text: bool = False
    ) -> NormalizedEvent:
        """Decode one bounded native record into source-linked observations.

        Parameters
        ----------
        record : SourceRecord
            Exact locator plus bounded bytes, or an explicit oversized-payload gap.
        full_text : bool
            Keep full extracted text for subsequent paging instead of search truncation.

        Returns
        -------
        NormalizedEvent
            Classification, attributed turn, status signal and best-effort-redacted text.
            Unknown/malformed/oversized records remain explicit categories.

        Notes
        -----
        No execution or I/O. Turn attribution carries the latest observed ID when a
        record omits it. Tool stdout and event messages are opaque to status detection.
        """
        if record.data is None:
            return NormalizedEvent(
                locator=record.locator, native_type="unknown", kind="oversized"
            )
        try:
            value = json.loads(record.data)
        except (ValueError, UnicodeDecodeError, RecursionError):
            return NormalizedEvent(
                locator=record.locator, native_type="invalid_json", kind="malformed"
            )
        if not isinstance(value, dict):
            return NormalizedEvent(
                locator=record.locator, native_type="invalid_shape", kind="malformed"
            )
        outer = value.get("type") if isinstance(value.get("type"), str) else "unknown"
        payload = value.get("payload", {})
        if not isinstance(payload, dict):
            return NormalizedEvent(
                locator=record.locator, native_type=str(outer), kind="unknown"
            )
        native = payload.get("type") if isinstance(payload.get("type"), str) else ""
        metadata = payload.get("internal_chat_message_metadata_passthrough")
        metadata = metadata if isinstance(metadata, dict) else {}
        turn = payload.get("turn_id", metadata.get("turn_id"))
        if isinstance(turn, str):
            self.turn_id = turn
        event = NormalizedEvent(
            locator=record.locator,
            native_type=str(outer) + (":" + str(native) if native else ""),
            kind="unknown",
            timestamp=(
                value.get("timestamp")
                if isinstance(value.get("timestamp"), str)
                else None
            ),
            turn_id=self.turn_id,
            phase=(
                payload.get("phase", payload.get("channel"))
                if isinstance(payload.get("phase", payload.get("channel")), str)
                else None
            ),
            message_id=(
                payload.get("id") if isinstance(payload.get("id"), str) else None
            ),
            call_id=(
                payload.get("call_id")
                if isinstance(payload.get("call_id"), str)
                else None
            ),
        )
        text = ""
        if outer == "response_item" and native == "message":
            event.kind, event.role = "message", (
                payload.get("role") if isinstance(payload.get("role"), str) else None
            )
            text = self._message(payload.get("content"))
        elif outer == "response_item" and native in {
            "function_call",
            "custom_tool_call",
        }:
            event.kind, event.name = "call", (
                payload.get("name") if isinstance(payload.get("name"), str) else None
            )
            text = self._text(payload.get("arguments", payload.get("input", "")))
        elif outer == "response_item" and native in {
            "function_call_output",
            "custom_tool_call_output",
        }:
            event.kind = "result"
            output = payload.get("output", "")
            text = (
                self._message(output)
                if isinstance(output, list)
                else self._text(output)
            )
            event.failure = self._failure(output)
            if payload.get("is_error") is True:
                event.failure = True
        elif outer == "event_msg" and native in {"user_message", "agent_message"}:
            event.kind, event.role = "message_observation", (
                "user" if native == "user_message" else "assistant"
            )
            text = self._text(payload.get("message", ""))
        elif "compact" in str(outer).lower() or "compact" in str(native).lower():
            event.kind = "compaction"
            text = self._text(payload.get("summary", payload.get("message", "")))
        elif outer in {
            "session_meta",
            "turn_context",
            "world_state",
            "inter_agent_communication_metadata",
        }:
            event.kind = "metadata"
        elif (
            outer == "token_usage_record"
            or outer == "event_msg"
            and native == "token_count"
        ):
            event.kind = "usage"
        elif outer == "response_item" and native == "agent_message":
            event.kind = "delegation_message"
            text = self._message(payload.get("content", payload.get("message")))
        elif outer == "event_msg":
            event.kind, event.name = "observation", str(native)
            event.failure = self._observation_failure(payload)
            text = self._text(payload.get("message", payload.get("reason", "")))
        elif outer == "response_item" and native in {"reasoning", "compaction"}:
            event.kind = "reasoning" if native == "reasoning" else "compaction"
            text = self._message(payload.get("summary", payload.get("content")))
        text = self.redactor.text(text)
        event.text_truncated = (
            not full_text and len(text) > self.settings.search_characters
        )
        event.text = text if full_text else text[: self.settings.search_characters]
        return event

    def _text(self, value) -> str:
        """Preserve text or serialize an already bounded external JSON value."""
        return (
            value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        )

    def _message(self, content) -> str:
        """Extract explicit text blocks; exclude binary/image payloads from search."""
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return ""
        return "\n".join(
            item["text"]
            for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        )

    def _failure(self, value) -> bool | None:
        """Read only the observed outer exec envelope; never recurse into stdout.

        Other native/tool formats remain unknown. This is a format-scoped wrapper
        signal, not authentication of arbitrary transcript content or proof that
        the requested user workflow succeeded.
        """
        if not isinstance(value, list) or len(value) != 2:
            return None
        if any(
            not isinstance(block, dict) or block.get("type") != "input_text"
            for block in value
        ):
            return None
        header, body = (block.get("text") for block in value)
        if not isinstance(header, str) or not isinstance(body, str):
            return None
        if not re.fullmatch(
            r"Script completed\nWall time [0-9]+(?:\.[0-9]+)? seconds\nOutput:\n?",
            header,
        ):
            return None
        try:
            envelope = json.loads(body)
        except (ValueError, RecursionError):
            return None
        if not isinstance(envelope, dict):
            return None
        if not (
            isinstance(envelope.get("chunk_id"), str)
            and type(envelope.get("wall_time_seconds")) in {int, float}
            and isinstance(envelope.get("output"), str)
            and type(envelope.get("exit_code")) is int
        ):
            return None
        return envelope["exit_code"] != 0

    @staticmethod
    def _observation_failure(payload: dict) -> bool | None:
        """Read native top-level observation status; message text stays opaque."""
        if payload.get("is_error") is True:
            return True
        status = payload.get("status")
        if isinstance(status, str) and status in {"failed", "error", "timeout"}:
            return True
        if type(payload.get("exit_code")) is int:
            return payload["exit_code"] != 0
        return None
