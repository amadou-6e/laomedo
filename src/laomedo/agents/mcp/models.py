"""Non-secret frozen identities for selected external MCP tools."""

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field, JsonValue


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

    def digest(self) -> str:
        """Hash semantic identities and schemas without runtime endpoints or secrets."""
        payload = sorted(
            (item.model_dump(mode="json") for item in self.tools),
            key=lambda item: (item["server"], item["upstream_name"]),
        )
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()
