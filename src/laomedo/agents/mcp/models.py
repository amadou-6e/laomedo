"""Non-secret frozen identities for selected external MCP tools."""

import hashlib
import json
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, SecretStr, field_validator
from laomedo.agents.mcp.settings import MAX_MANIFEST_BYTES


class McpTool(BaseModel):
    """Describe one exact upstream tool without retaining native client state."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    server: str = Field(min_length=1, max_length=256, description="Native server name.")
    upstream_name: str = Field(
        min_length=1,
        max_length=256,
        description="Original MCP tool name before UI aliases.",
    )
    display_name: str = Field(
        min_length=1,
        max_length=256,
        description="Selected native tool's display alias.",
    )
    description: str = Field(
        max_length=16000, description="Untrusted tool description."
    )
    input_schema: dict[str, JsonValue] = Field(
        description="Frozen JSON schema used to validate invocation arguments."
    )

    def external_name(self) -> str:
        """Return a stable collision-resistant name outside internal tool namespaces."""
        identity = json.dumps([self.server, self.upstream_name], ensure_ascii=False)
        return "external_" + hashlib.sha256(identity.encode()).hexdigest()[:32]


class McpManifest(BaseModel):
    """Canonical selected-tool set participating in request and resume identity."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    tools: tuple[McpTool, ...] = Field(
        min_length=1,
        max_length=128,
        description="Exact selected tools in canonical order.",
    )

    @field_validator("tools")
    @classmethod
    def canonical_tools(cls, value):
        """Canonicalize order and reject ambiguous identities before request hashing."""
        identities = {(tool.server, tool.upstream_name) for tool in value}
        if len(identities) != len(value) or len({tool.server for tool in value}) > 32:
            raise ValueError("mcp_manifest_invalid")
        if (
            len(json.dumps([tool.model_dump(mode="json") for tool in value]).encode())
            > MAX_MANIFEST_BYTES
        ):
            raise ValueError("mcp_manifest_too_large")
        return tuple(sorted(value, key=lambda tool: (tool.server, tool.upstream_name)))

    def digest(self) -> str:
        """Hash semantic identities and schemas without runtime endpoints or secrets."""
        payload = sorted(
            (item.model_dump(mode="json") for item in self.tools),
            key=lambda item: (item["server"], item["upstream_name"]),
        )
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()


class McpRegistration(BaseModel):
    """Public transient admission reference; never an upstream credential."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    registration_id: UUID = Field(
        description="Opaque locally published invocation registration."
    )
    manifest: McpManifest = Field(
        description="Frozen semantic tool identity for admission."
    )


class McpConnection(BaseModel):
    """Host-private forwarding capability, excluded from ordinary serialization."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    registration: McpRegistration = Field(
        description="Non-secret registration and manifest."
    )
    port: int = Field(ge=1, le=65535, description="Private forwarding server TCP port.")
    bind: str = Field(
        description="Host-local interface used for authenticated supervision."
    )
    controller_host: str = Field(
        description="Host alias visible to isolated controllers."
    )
    token: SecretStr = Field(
        min_length=43,
        max_length=43,
        exclude=True,
        repr=False,
        description="Invocation-scoped bearer capability; never upstream login material.",
    )

    def private_payload(self) -> dict:
        """Project the capability only for the private atomic rendezvous file."""
        return {**self.model_dump(mode="json"), "token": self.token.get_secret_value()}

    def endpoint(self, *, controller: bool = False) -> str:
        """Construct a private forwarding endpoint without placing its token in a URL."""
        host = self.controller_host if controller else self.bind
        return f"http://{host}:{self.port}/{self.registration.registration_id}/mcp"


class McpLease(BaseModel):
    """Mutable app-owned registration state; live native tools never serialize."""

    model_config = ConfigDict(arbitrary_types_allowed=True, hide_input_in_errors=True)
    connection: McpConnection = Field(
        exclude=True,
        repr=False,
        description="Host-private endpoint and bearer capability.",
    )
    tools: dict[str, Any] = Field(
        exclude=True,
        repr=False,
        description="Exact admitted native adapters keyed by external tool name.",
    )
    expires: float = Field(
        description="Monotonic expiry deadline maintained by the owner."
    )
    run_id: UUID | None = Field(
        default=None,
        description="Exact runner invocation owning this registration after admission.",
    )
    tasks: dict[Any, Any] = Field(
        default_factory=dict,
        exclude=True,
        repr=False,
        description="Owned in-flight call tasks, cancelled on revocation; effects may remain unknown.",
    )
