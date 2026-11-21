"""Claude built-in admission and native compaction completion evidence."""

import hashlib
import json

from laomedo.agents.agents.base.acp.models import NativeCommandCatalog
from laomedo.agents.agents.base.models import NativeCommandDiscovery
from laomedo.agents.agents.claude.models import ClaudeCommandResult
from laomedo.agents.agents.claude.settings import CLI_VERSION
from laomedo.agents.errors import RunnerError


class ClaudeCommands:
    """Admit only observed built-ins with a supported isolated completion path."""

    @classmethod
    def validate(cls, command):
        """The initial supported built-in is compaction without arguments."""
        if command.name != "compact":
            raise RunnerError("native_command_not_supported")
        if command.arguments:
            raise RunnerError("native_command_arguments_invalid")

    @classmethod
    def revision(cls, catalog, image_id):
        """Bind observed entries to the actual provider, pinned handler and image."""
        return hashlib.sha256(
            json.dumps(
                {
                    "provider": "claude",
                    "cli": CLI_VERSION,
                    "adapter": "0.98.0",
                    "image_id": image_id,
                    "catalog": catalog.model_dump(mode="json"),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    @classmethod
    def project(cls, value, image_id, *, builtins_only):
        """Untrusted catalog names alone do not establish built-in provenance."""
        catalog = NativeCommandCatalog.model_validate(value)
        return NativeCommandDiscovery(
            state="available",
            revision=cls.revision(catalog, image_id),
            commands=[
                {
                    "name": item.name,
                    "description": item.description,
                    "input_hint": item.input.hint if item.input else None,
                    "executable": builtins_only and item.name == "compact",
                    "accepts_arguments": False,
                    "may_use_model": (
                        True if builtins_only and item.name == "compact" else None
                    ),
                    "reason": (
                        None
                        if builtins_only and item.name == "compact"
                        else "outside_assistant_command_policy"
                    ),
                }
                for item in catalog.commands
            ],
        ).model_dump(mode="json")

    @classmethod
    def admit(cls, command, catalog, image_id, *, builtins_only):
        """Check provenance, live advertisement and exact handler-bound revision."""
        cls.validate(command)
        if not builtins_only:
            raise RunnerError("native_command_context_invalid")
        if (
            catalog is None
            or cls.revision(catalog, image_id) != command.catalog_revision
        ):
            raise RunnerError("native_command_catalog_changed")
        if not any(item.name == command.name for item in catalog.commands):
            raise RunnerError("native_command_not_available")

    @classmethod
    def result(cls, events, thread, stop_reason):
        """Require root-session native compaction evidence, never ordinary model prose."""
        if stop_reason != "end_turn":
            raise RunnerError("claude_native_turn_failed")
        started = False
        terminal = None
        for event in events:
            if event.get("session_id") != thread or event.get("parent_tool_use_id"):
                continue
            if event.get("type") == "result" and (
                event.get("is_error") or event.get("subtype") != "success"
            ):
                raise RunnerError("claude_native_turn_failed")
            if event.get("type") != "system":
                continue
            if event.get("compact_result") == "failed":
                raise RunnerError("claude_native_turn_failed")
            if event.get("status") == "compacting":
                started = True
            boundary = event.get("subtype") == "compact_boundary"
            if boundary or (started and event.get("compact_result") == "success"):
                identity = event.get("uuid")
                if not isinstance(identity, str) or not identity:
                    raise RunnerError("claude_terminal_receipt_invalid")
                terminal = {
                    "kind": "compact_boundary" if boundary else "compact_result",
                    "event_id": identity,
                    "session_id": thread,
                }
        if terminal is None:
            raise RunnerError("claude_terminal_receipt_invalid")
        return ClaudeCommandResult(command="compact", native_terminal=terminal)
