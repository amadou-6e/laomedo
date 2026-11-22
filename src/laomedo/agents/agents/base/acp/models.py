"""Results derived from observed ACP updates and terminal prompt responses."""

from pydantic import BaseModel, Field, ConfigDict
import hashlib
import json


class NativeCommandInput(BaseModel):
    """A bounded native argument hint, without an executable argument schema."""

    model_config = ConfigDict(extra="ignore", strict=True, frozen=True)
    hint: str = Field(
        max_length=4000,
        description="Provider-authored text describing accepted arguments.",
    )


class NativeSkillSource(BaseModel):
    """Native skill provenance reported by the pinned provider adapter."""

    model_config = ConfigDict(extra="ignore", strict=True, frozen=True)
    name: str = Field(min_length=1, max_length=200)
    path: str = Field(min_length=1, max_length=1000)
    scope: str = Field(min_length=1, max_length=100)
    enabled: bool


class NativeCommandProvenance(BaseModel):
    """Native built-in marker or system-skill source, never a host grant."""

    model_config = ConfigDict(extra="ignore", strict=True, frozen=True)
    builtin: bool | None = None
    skill: NativeSkillSource | None = None


class NativeCommandMetadata(BaseModel):
    """Provider metadata is observation, never permission to execute a skill."""

    model_config = ConfigDict(extra="ignore", strict=True, frozen=True)
    laomedo: NativeCommandProvenance = Field(default_factory=NativeCommandProvenance)


class NativeCommand(BaseModel):
    """A provider-advertised command, without granting execution permission."""

    model_config = ConfigDict(
        extra="ignore", strict=True, frozen=True, populate_by_name=True
    )
    metadata: NativeCommandMetadata | None = Field(default=None, alias="_meta")
    name: str = Field(
        min_length=1,
        max_length=200,
        description="Exact native command identifier, without a leading slash.",
    )
    description: str = Field(
        max_length=4000,
        description="Untrusted provider description for display, never execution authority.",
    )
    input: NativeCommandInput | None = Field(
        default=None, description="Native argument hint when the provider reports one."
    )


class NativeCommandCatalog(BaseModel):
    """Detached, bounded observation of a session's complete native command list."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    commands: list[NativeCommand] = Field(
        max_length=256,
        description="Latest complete advertised list; empty explicitly clears older commands.",
    )

    def revision(self) -> str:
        """Hash canonical observed metadata; the digest grants no execution authority."""
        value = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(value.encode()).hexdigest()


class AcpTurn(BaseModel):
    """One terminal prompt outcome; interruption never implies successful work."""

    session_id: str = Field(description="Agent's native persisted session identity.")
    stop_reason: str = Field(description="Unmodified ACP terminal stop reason.")
    answer: str = Field(description="Ordered text from this prompt's agent messages.")
    updates: list[dict] = Field(
        description="Observed ACP updates for this prompt only."
    )
    usage: dict | None = Field(
        default=None,
        description="Native ACP usage when supplied; absent means unknown.",
    )

    def tool_calls(self) -> list[dict]:
        """Project final observed ACP tool states without inventing native IDs."""
        calls = {}
        for update in self.updates:
            if update.get("sessionUpdate") not in {"tool_call", "tool_call_update"}:
                continue
            identity = update.get("toolCallId")
            if not isinstance(identity, str):
                continue
            calls.setdefault(identity, {}).update(update)
        return [
            {
                "call_id": identity,
                "tool": value.get("title"),
                "status": value.get("status"),
                "input": value.get("rawInput"),
                "output": value.get("rawOutput", value.get("content")),
                "error": value.get("status") == "failed",
            }
            for identity, value in calls.items()
        ]
