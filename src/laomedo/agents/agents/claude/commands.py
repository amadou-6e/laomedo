"""Claude built-in admission and native compaction completion evidence."""

import hashlib
import json

from laomedo.agents.agents.base.acp.models import NativeCommandCatalog
from laomedo.agents.agents.base.models import NativeCommandDiscovery
from laomedo.agents.agents.claude.models import ClaudeCommandResult
from laomedo.agents.agents.claude.models import ClaudeControlResult
from laomedo.agents.agents.claude.settings import CLI_VERSION
from laomedo.agents.errors import RunnerError


class ClaudeCommands:
    """Admit only observed built-ins with a supported isolated completion path."""

    @classmethod
    def builtin_skills(cls, buffered, session_id):
        """Read the actual SDK initialization skill list for this isolated session."""
        observed = []
        for _, params in buffered:
            event = params.get("message")
            if (
                params.get("sessionId") != session_id
                or not isinstance(event, dict)
                or event.get("type") != "system"
                or event.get("subtype") != "init"
                or event.get("session_id") != session_id
            ):
                continue
            names = event.get("skills")
            if (
                not isinstance(names, list)
                or len(names) > 256
                or any(
                    not isinstance(name, str) or not 0 < len(name) <= 200
                    for name in names
                )
                or len(set(names)) != len(names)
            ):
                return ()
            observed.append(tuple(sorted(names)))
        return observed[0] if len(observed) == 1 else ()

    @classmethod
    def validate(cls, command):
        """Admit compaction and read-only native control views without arguments."""
        if command.name not in {"compact", "usage", "context", "mcp"}:
            raise RunnerError("native_command_not_supported")
        if command.arguments:
            raise RunnerError("native_command_arguments_invalid")

    @classmethod
    def revision(cls, catalog, image_id, *, builtin_skills=()):
        """Bind observed entries to the actual provider, pinned handler and image."""
        return hashlib.sha256(
            json.dumps(
                {
                    "provider": "claude",
                    "cli": CLI_VERSION,
                    "adapter": "0.98.0",
                    "image_id": image_id,
                    "catalog": catalog.model_dump(mode="json"),
                    "builtin_skills": sorted(builtin_skills),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    @classmethod
    def project(cls, value, image_id, *, builtins_only, builtin_skills=()):
        """Untrusted catalog names alone do not establish built-in provenance."""
        catalog = NativeCommandCatalog.model_validate(value)
        return NativeCommandDiscovery(
            state="available",
            revision=cls.revision(catalog, image_id, builtin_skills=builtin_skills),
            commands=[
                {
                    "name": item.name,
                    "kind": "skill" if item.name in builtin_skills else "command",
                    "description": item.description,
                    "input_hint": item.input.hint if item.input else None,
                    "executable": builtins_only
                    and item.name in {"compact", "usage", "context", "mcp"},
                    "accepts_arguments": False,
                    "may_use_model": (
                        item.name == "compact"
                        if builtins_only
                        and item.name in {"compact", "usage", "context", "mcp"}
                        else None
                    ),
                    "reason": (
                        None
                        if builtins_only
                        and item.name in {"compact", "usage", "context", "mcp"}
                        else (
                            "native_skill_requirements_unverified"
                            if item.name in builtin_skills
                            else "outside_assistant_command_policy"
                        )
                    ),
                }
                for item in catalog.commands
            ],
        ).model_dump(mode="json")

    @classmethod
    def admit(cls, command, catalog, image_id, *, builtins_only, builtin_skills=()):
        """Check provenance, live advertisement and exact handler-bound revision."""
        cls.validate(command)
        if not builtins_only:
            raise RunnerError("native_command_context_invalid")
        if (
            catalog is None
            or cls.revision(catalog, image_id, builtin_skills=builtin_skills)
            != command.catalog_revision
        ):
            raise RunnerError("native_command_catalog_changed")
        if not any(item.name == command.name for item in catalog.commands):
            raise RunnerError("native_command_not_available")

    @classmethod
    def result(cls, events, thread, stop_reason, *, command="compact", answer=None):
        """Require command-specific root native evidence, never ordinary model prose."""
        if command in {"usage", "context", "mcp"}:
            return cls.control_result(events, thread, stop_reason, command, answer)
        if command != "compact":
            raise RunnerError("native_command_not_supported")
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

    @classmethod
    def control_result(cls, events, thread, stop_reason, command, answer):
        """Require a root native local-output receipt and terminal ACP response.

        Missing local evidence, native failure and any reported model output all
        refuse completion. The ACP text is the actual control view, not a model
        response or proof that a session setting changed.
        """
        if command not in {"usage", "context", "mcp"}:
            raise RunnerError("native_command_not_supported")
        if stop_reason != "end_turn":
            raise RunnerError("claude_native_turn_failed")
        terminal = None
        result_seen = False
        result_command = None
        for event in events:
            if event.get("session_id") != thread or event.get("parent_tool_use_id"):
                continue
            if event.get("is_error") or (
                event.get("type") == "result" and event.get("subtype") != "success"
            ):
                raise RunnerError("claude_native_turn_failed")
            if event.get("type") == "result":
                usage = event.get("usage")
                if not isinstance(usage, dict) or usage.get("output_tokens") != 0:
                    raise RunnerError("claude_terminal_receipt_invalid")
                result_seen = True
                result_command = event.get("local_command")
            local_run = event.get("local_command_run")
            if event.get("type") == "assistant" and isinstance(local_run, dict):
                if local_run.get("command") != command or local_run.get("args") != "":
                    raise RunnerError("claude_terminal_receipt_invalid")
                identity = event.get("uuid")
                if not isinstance(identity, str) or not identity:
                    raise RunnerError("claude_terminal_receipt_invalid")
                terminal = {
                    "kind": "local_command_run",
                    "event_id": identity,
                    "session_id": thread,
                }
            if (
                event.get("type") == "system"
                and event.get("subtype") == "local_command_output"
            ):
                identity = event.get("uuid")
                if not isinstance(identity, str) or not identity:
                    raise RunnerError("claude_terminal_receipt_invalid")
                terminal = {
                    "kind": "local_command_output",
                    "event_id": identity,
                    "session_id": thread,
                }
        if (
            terminal is None
            or not result_seen
            or (
                terminal.get("kind") == "local_command_run"
                and result_command != command
            )
            or not isinstance(answer, str)
            or not answer.strip()
            or len(answer) > 1048576
        ):
            raise RunnerError("claude_terminal_receipt_invalid")
        return ClaudeControlResult(
            command=command, native_terminal=terminal, answer=answer
        )
