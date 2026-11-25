"""Codex built-in command admission; native descriptions never grant authority."""

from laomedo.agents.agents.base.models import NativeCommandInvocation
from laomedo.agents.agents.base.models import NativeCommandDiscovery
from laomedo.agents.agents.base.acp.models import NativeCommandCatalog
from laomedo.agents.errors import RunnerError
from laomedo.agents.agents.codex.settings import BUNDLED_SKILL_REQUIREMENTS
from laomedo.agents.agents.codex.controller.models import CodexSkillReceipt
from pydantic import ValidationError
import re


class CodexCommands:
    """Intersect observed native commands with the supported assistant policy."""

    @classmethod
    def skill_mentions(cls, text):
        """Mirror the pinned native ASCII token and linked-path selection rules."""
        names = {"$" + name for name in re.findall(r"\$([A-Za-z0-9_:-]+)", text)}
        for path in re.findall(r"\[\$[A-Za-z0-9_:-]+\][\t\n\v\f\r ]*\(([^)]*)\)", text):
            path = path.strip().removeprefix("skill://").replace("\\", "/")
            for name in BUNDLED_SKILL_REQUIREMENTS:
                if (
                    path
                    == "/home/runner/.codex/skills/.system/" + name[1:] + "/SKILL.md"
                ):
                    names.add(name)
        return names.intersection(BUNDLED_SKILL_REQUIREMENTS)

    @classmethod
    def validate_skill_mentions(cls, text, command=None):
        """Refuse native text-triggered injection outside the approved skill."""
        allowed = (
            {command.name}
            if command is not None and command.name.startswith("$")
            else set()
        )
        if cls.skill_mentions(text) - allowed:
            raise RunnerError("native_skill_approval_required")

    @classmethod
    def skill_receipt(cls, events, command, *, session_id, turn_id, invocation_id):
        """Require ordered adapter input proof inside this exact native root turn."""
        markers = [
            (index, event.get("params", {}))
            for index, event in enumerate(events)
            if event.get("method") == "laomedo/skillInput"
        ]
        starts = [
            index
            for index, event in enumerate(events)
            if event.get("method") == "turn/started"
            and event.get("params", {}).get("threadId") == session_id
            and event.get("params", {}).get("turn", {}).get("id") == turn_id
        ]
        ends = [
            index
            for index, event in enumerate(events)
            if event.get("method") == "turn/completed"
            and event.get("params", {}).get("threadId") == session_id
            and event.get("params", {}).get("turn", {}).get("id") == turn_id
        ]
        if len(markers) != 1 or len(starts) != 1 or len(ends) != 1:
            raise RunnerError("native_command_outcome_unknown")
        index, value = markers[0]
        if (
            not starts[0] < index < ends[0]
            or value.get("origin") != "laomedo_adapter"
            or value.get("phase") != "native_turn_accepted"
            or value.get("threadId") != session_id
            or value.get("turnId") != turn_id
            or value.get("invocationId") != invocation_id
            or "$" + str(value.get("name")) != command.name
            or value.get("path")
            != "/home/runner/.codex/skills/.system/" + command.name[1:] + "/SKILL.md"
        ):
            raise RunnerError("native_command_outcome_unknown")
        try:
            return CodexSkillReceipt(
                invocation_id=invocation_id,
                session_id=session_id,
                turn_id=turn_id,
                name=value["name"],
                path=value["path"],
                manifest_sha256=value.get("manifestSha256"),
            )
        except ValidationError:
            raise RunnerError("native_command_outcome_unknown") from None

    @classmethod
    def validate(cls, request: NativeCommandInvocation) -> str:
        """Return completion class after checking exact supported argument grammar."""
        if request.name in {"status", "mcp", "skills"}:
            kind = "control"
        elif request.name in {"review", "compact", "$skill-creator"}:
            kind = "turn"
        else:
            raise RunnerError("native_command_not_supported")
        if request.name not in {"review", "$skill-creator"} and request.arguments:
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
        if request.name.startswith("$"):
            item = next(item for item in catalog.commands if item.name == request.name)
            if cls.skill_reason(item, catalog) is not None:
                raise RunnerError("native_command_not_available")
        return kind

    @classmethod
    def skill_reason(cls, item, catalog):
        """Require unambiguous native system scope/path and a supported capability."""
        source = item.metadata.laomedo.skill if item.metadata else None
        if (
            source is None
            or source.scope != "system"
            or not source.enabled
            or item.name != "$" + source.name
            or source.path
            != "/home/runner/.codex/skills/.system/" + source.name + "/SKILL.md"
            or sum(entry.name == item.name for entry in catalog.commands) != 1
        ):
            return "native_skill_source_unverified"
        return BUNDLED_SKILL_REQUIREMENTS.get(
            item.name, "native_skill_requirements_unverified"
        )

    @classmethod
    def project(cls, value):
        """Expose bounded observed commands with explicit unsupported reasons."""
        catalog = NativeCommandCatalog.model_validate(value)
        commands = []
        for item in catalog.commands:
            skill = item.name.startswith("$")
            reason = (
                cls.skill_reason(item, catalog)
                if skill
                else "outside_assistant_command_policy"
            )
            supported = (
                reason is None
                if skill
                else item.name in {"status", "mcp", "skills", "review", "compact"}
            )
            commands.append(
                {
                    "name": item.name,
                    "kind": "skill" if skill else "command",
                    "description": item.description,
                    "input_hint": item.input.hint if item.input else None,
                    "executable": supported,
                    "accepts_arguments": supported and (item.name == "review" or skill),
                    "may_use_model": (
                        item.name in {"review", "compact"} or skill
                        if supported
                        else None
                    ),
                    "reason": None if supported else reason,
                }
            )
        return NativeCommandDiscovery(
            state="available", revision=catalog.revision(), commands=commands
        ).model_dump(mode="json")
