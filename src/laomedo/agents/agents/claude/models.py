"""Canonical host-owned Claude policy, shared by launch and run binding."""

import hashlib
import json
from pydantic import BaseModel, ConfigDict, Field
from laomedo.agents.agents.claude.settings import SYSTEM
from pathlib import Path
from uuid import UUID
from typing import Any
from pydantic import SecretStr
from laomedo.agents.connections.models import ConnectionRecord, LoginProgress


class ClaudeCommandResult(BaseModel):
    """A native command receipt, distinct from a model-turn answer or usage."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    command: str = Field(description="Exact admitted built-in command.")
    native_terminal: dict[str, str] = Field(
        description="Observed root native completion identity, without transcript content."
    )


class ClaudeControlResult(ClaudeCommandResult):
    """Native local-command output, without an invented model turn or usage."""

    answer: str = Field(
        min_length=1,
        max_length=1048576,
        description="Actual ACP text produced by the admitted native read-only command.",
    )


class ClaudePolicy(BaseModel):
    """Group native model selection, pinned skills and available tool scope."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    model: str = Field(
        description="Resolved native model selected from runtime metadata."
    )
    effort: str = Field(description="Requested supported effort, or native default.")
    skill_ids: tuple[str, ...] = Field(
        default=(), description="Exact pinned skill IDs available to this invocation."
    )
    output_only: bool = Field(
        default=False, description="Correction scope with all execution tools disabled."
    )
    external_tools: tuple[str, ...] = Field(
        default=(), description="Exact frozen external MCP tool names, never wildcards."
    )

    def sdk_options(self):
        """Return exactly the policy passed through the Claude ACP adapter."""
        options = {
            "model": self.model,
            "tools": ["Skill"] if self.skill_ids and not self.output_only else [],
            "allowedTools": (
                []
                if self.output_only
                else [
                    "mcp__laomedo__exec_command",
                    "mcp__laomedo__github_operation",
                    *["Skill(laomedo-pinned:" + item + ")" for item in self.skill_ids],
                    *["mcp__external__" + item for item in self.external_tools],
                ]
            ),
            "disallowedTools": [
                "Read",
                "Glob",
                "Grep",
                "Edit",
                "Write",
                "Bash",
                "Agent",
                "Task",
                "WebFetch",
                "WebSearch",
                "NotebookEdit",
            ],
            "settingSources": [],
            "settings": {
                "disableAllHooks": True,
                "enabledPlugins": {},
                "autoMemoryEnabled": False,
                "syncClaudeAiSkills": False,
                "syncClaudeAiPlugins": False,
            },
            "allowDangerouslySkipPermissions": False,
            "promptSuggestions": False,
            "systemPrompt": SYSTEM,
            "extraArgs": {
                "restricted": None,
                "permission-prompts": "none",
                "strict-mcp-config": None,
            },
        }
        if self.effort != "default":
            options["effort"] = self.effort
        if not self.output_only:
            options["plugins"] = [
                {"type": "local", "path": "/run/laomedo/pinned-skills"}
            ]
        return options

    def fingerprint(self):
        """Bind saved runs to their actual ACP policy, never a retired CLI argv."""
        return (
            "sha256:"
            + hashlib.sha256(
                json.dumps(
                    self.sdk_options(), sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
        )


class ClaudeNativeProfile(BaseModel):
    """Host-only ownership of a native volume; never a credential projection."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = Field(
        pattern=r"^laomedo-claude-connection-[0-9a-f]{32}$",
        description="Opaque Docker volume name selected by this host.",
    )
    labels: dict[str, str] = Field(
        repr=False,
        description="Exact SDK ownership labels required before volume mutation.",
    )
    docker_endpoint: str = Field(
        repr=False,
        description="Original daemon endpoint; never switch daemons during recovery.",
    )
    image_id: str = Field(
        pattern=r"^sha256:[0-9a-f]{64}$",
        description="Immutable official-client image used for authentication.",
    )


class ClaudeAccountIdentity(BaseModel):
    """Public account/workspace identity verified by official native auth status."""

    email: str = Field(
        min_length=1,
        max_length=100,
        description="Native client's provider-verified account email.",
    )
    organization_id: str = Field(
        min_length=1, description="Native client's verified workspace identifier."
    )

    def subject_hash(self) -> str:
        """Return the stable local account/workspace digest without any token input."""
        return hashlib.sha256(
            json.dumps(
                {"email": self.email.casefold(), "orgId": self.organization_id},
                sort_keys=True,
            ).encode()
        ).hexdigest()


class ClaudeLoginAttempt(BaseModel):
    """Process-local native login; every live handle and URL is excluded."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    profile_id: UUID = Field(
        exclude=True, description="Authenticated local profile owning the attempt."
    )
    lease_hash: str = Field(
        exclude=True,
        repr=False,
        description="Originating browser lease, fenced on logout.",
    )
    candidate_id: UUID = Field(
        exclude=True, description="New or reconnecting saved connection."
    )
    credential_id: UUID = Field(
        exclude=True, description="Fresh immutable native volume revision."
    )
    previous: ConnectionRecord | None = Field(
        default=None,
        exclude=True,
        description="Committed connection preserved until successful replacement.",
    )
    expires_at: float = Field(
        exclude=True, description="Monotonic native attempt expiry."
    )
    progress: LoginProgress = Field(description="Safe observable attempt state.")
    authorization_url: SecretStr | None = Field(
        default=None,
        exclude=True,
        repr=False,
        description="Official-client URL, only relayed to the owning browser.",
    )
    session: Any = Field(
        default=None,
        exclude=True,
        repr=False,
        description="Live creator-owned native stdin session.",
    )
    cancelled: Any = Field(
        exclude=True,
        repr=False,
        description="Cancellation event observed by the native lifecycle.",
    )
    ready: Any = Field(
        exclude=True,
        repr=False,
        description="Event announcing a URL or a terminal failure.",
    )
    worker: Any = Field(
        default=None,
        exclude=True,
        repr=False,
        description="Owning worker; joined before final store closure.",
    )
    submitted: bool = Field(
        default=False,
        exclude=True,
        description="Whether this attempt consumed its one code submission.",
    )
    settled: bool = Field(
        default=False,
        exclude=True,
        description="Whether native session cleanup and publication have settled.",
    )
