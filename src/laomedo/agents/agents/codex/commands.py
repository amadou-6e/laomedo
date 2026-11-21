"""Codex built-in command admission; native descriptions never grant authority."""

from laomedo.agents.agents.base.models import NativeCommandInvocation
from laomedo.agents.agents.base.models import NativeCommandDiscovery
from laomedo.agents.agents.base.acp.models import NativeCommandCatalog
from laomedo.agents.errors import RunnerError


class CodexCommands:
    """Intersect observed native commands with the supported assistant policy."""

    @classmethod
    def validate(cls, request: NativeCommandInvocation) -> str:
        """Return completion class after checking exact supported argument grammar."""
        if request.name in {"status", "mcp", "skills"}:
            kind = "control"
        elif request.name in {"review", "compact"}:
            kind = "turn"
        else:
            raise RunnerError("native_command_not_supported")
        if request.name != "review" and request.arguments:
            raise RunnerError("native_command_arguments_invalid")
        return kind

    @classmethod
    def admit(cls, request, catalog):
        """Require current native advertisement and exact approved metadata digest."""
        kind = cls.validate(request)
        if catalog is None or catalog.revision() != request.catalog_revision:
            raise RunnerError("native_command_catalog_changed")
        if not any(item.name == request.name for item in catalog.commands):
            raise RunnerError("native_command_not_available")
        return kind

    @classmethod
    def project(cls, value):
        """Expose bounded observed commands with explicit unsupported reasons."""
        catalog = NativeCommandCatalog.model_validate(value)
        commands = []
        for item in catalog.commands:
            supported = item.name in {"status", "mcp", "skills", "review", "compact"}
            commands.append(
                {
                    "name": item.name,
                    "description": item.description,
                    "input_hint": item.input.hint if item.input else None,
                    "executable": supported,
                    "accepts_arguments": supported and item.name == "review",
                    "may_use_model": (
                        item.name in {"review", "compact"} if supported else None
                    ),
                    "reason": None if supported else "outside_assistant_command_policy",
                }
            )
        return NativeCommandDiscovery(
            state="available", revision=catalog.revision(), commands=commands
        ).model_dump(mode="json")
