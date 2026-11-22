"""Pinned OpenCode built-ins with explicit command and child-result admission."""

import hashlib
import json

from laomedo.agents.agents.base.acp.models import NativeCommandCatalog
from laomedo.agents.agents.base.models import NativeCommandDiscovery
from laomedo.agents.agents.opencode.models import OpenCodeCommandResult
from laomedo.agents.agents.opencode.settings import CLI_VERSION
from laomedo.agents.errors import RunnerError


class OpenCodeCommands:
    """Native command execution does not bypass controller/worker isolation."""

    # Pinned OpenCode 1.18.33 mcp/catalog.ts:fetch always keys prompts as
    # sanitizedClient + ":" + sanitizedPrompt. They cannot overwrite the bare
    # init/review built-ins. Host config has no command overrides or plugins;
    # custom startup configuration and skills fail builtins_only admission.

    @classmethod
    def validate(cls, command):
        """Refuse arguments: upstream expands shell interpolation before tool checks."""
        if command.name not in {"init", "review"}:
            raise RunnerError("native_command_not_supported")
        if command.arguments:
            raise RunnerError("native_command_arguments_invalid")

    @classmethod
    def revision(cls, catalog, image_id):
        """Bind the observed catalog to its actual pinned native handler/image."""
        return hashlib.sha256(
            json.dumps(
                {
                    "provider": "opencode",
                    "version": CLI_VERSION,
                    "image_id": image_id,
                    "catalog": catalog.model_dump(mode="json"),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    @classmethod
    def project(cls, value, image_id, *, builtins_only):
        """Never invent compact or expose custom command execution authority."""
        catalog = NativeCommandCatalog.model_validate(value)
        return NativeCommandDiscovery(
            state="available",
            revision=cls.revision(catalog, image_id),
            commands=[
                {
                    "name": item.name,
                    "description": item.description,
                    "input_hint": item.input.hint if item.input else None,
                    "executable": builtins_only and item.name in {"init", "review"},
                    "accepts_arguments": False,
                    "may_use_model": (
                        True
                        if builtins_only and item.name in {"init", "review"}
                        else None
                    ),
                    "reason": (
                        None
                        if builtins_only and item.name in {"init", "review"}
                        else "outside_assistant_command_policy"
                    ),
                }
                for item in catalog.commands
            ],
        ).model_dump(mode="json")

    @classmethod
    def admit(cls, command, catalog, image_id, *, builtins_only):
        """Refuse unobserved or modified handlers before sending any slash text."""
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
    def result(cls, command, history, baseline, *, external_tools=()):
        """Require terminal error-free native work, including the review child task."""
        cls.validate(command)
        if baseline is None or not history.terminal_complete(baseline):
            raise RunnerError("opencode_response_not_terminal")
        root_messages = history.attempt_messages(history.root_id, baseline)
        roots = [
            item for item in root_messages if item["info"].get("role") == "assistant"
        ]
        if not roots:
            raise RunnerError("opencode_response_not_terminal")
        child_ids = []
        failed = False
        for identity in history.attempt_sessions(baseline):
            for message in history.attempt_messages(identity, baseline):
                if message["info"].get("role") == "assistant" and message["info"].get(
                    "error"
                ):
                    failed = True
                for part in message["parts"]:
                    if part.get("type") != "tool":
                        continue
                    state = part.get("state") or {}
                    if state.get("status") not in {"completed", "error"}:
                        raise RunnerError("opencode_response_not_terminal")
                    allowed = {
                        "laomedo_exec",
                        *("external_" + name for name in external_tools),
                    }
                    if part.get("tool") not in allowed and not (
                        command.name == "review"
                        and identity == history.root_id
                        and part.get("tool") == "task"
                    ):
                        raise RunnerError("opencode_response_not_terminal")
                    if identity == history.root_id and part.get("tool") == "task":
                        if state.get("status") != "completed":
                            raise RunnerError("opencode_response_not_terminal")
                        metadata = state.get("metadata") or {}
                        child = metadata.get("sessionId")
                        if (
                            metadata.get("parentSessionId") != history.root_id
                            or child not in history.sessions
                        ):
                            raise RunnerError("opencode_response_not_terminal")
                        child_ids.append(child)
                    failed = failed or state.get("status") == "error"
        if command.name == "review" and not child_ids:
            raise RunnerError("opencode_response_not_terminal")
        if failed:
            raise RunnerError("opencode_native_command_failed")
        return OpenCodeCommandResult(
            command=command.name,
            native_terminal={
                "target": "isolated_controller_view",
                "target_description": "Agent configuration only; no repository files or Git history. Worker writes are separate.",
                "session_id": history.root_id,
                "message_ids": [item["info"]["id"] for item in roots],
                "child_sessions": child_ids,
            },
        )
