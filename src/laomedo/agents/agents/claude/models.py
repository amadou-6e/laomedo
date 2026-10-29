"""Canonical host-owned Claude policy, shared by launch and run binding."""

import hashlib
import json
from pydantic import BaseModel, ConfigDict, Field
from laomedo.agents.agents.claude.settings import SYSTEM


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

    def sdk_options(self):
        """Return exactly the policy passed through the Claude ACP adapter."""
        options = {
            "model": self.model,
            "tools": ["Skill"] if self.skill_ids and not self.output_only else [],
            "allowedTools": []
            if self.output_only
            else [
                "mcp__laomedo__exec_command",
                "mcp__laomedo__github_operation",
                *["Skill(laomedo-pinned:" + item + ")" for item in self.skill_ids],
            ],
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
