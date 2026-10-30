"""Validated runtime inputs for the private native OpenCode configuration."""

from copy import deepcopy
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, SecretStr

from .settings import BROKER_HOST, CONFIG_SCHEMA_URL

PermissionAction = Literal["allow", "ask", "deny"]


class OpenCodeRuntimeIdentity(BaseModel):
    """Related controller/worker/profile bindings retained for native resume checks."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    provider: Literal["opencode"] = Field(
        default="opencode", description="Native provider identity."
    )
    runtime_version: str = Field(description="Existing pinned native CLI version.")
    image: str = Field(description="Configured controller image name.")
    image_id: str | None = Field(
        description="Existing controller image pin; preserve the legacy optional binding."
    )
    profile_id: JsonValue = Field(
        description="Existing persisted profile identity observation, without stricter historical admission."
    )
    worker_image: str = Field(
        description="Configured credential-free worker image name."
    )
    worker_image_id: str = Field(
        description="Selected immutable worker image identity."
    )
    credential_binding: str = Field(
        repr=False,
        description="Existing keyed credential fingerprint, never login material.",
    )

    def to_payload(self) -> dict:
        """Return exactly the native runtime fingerprint preimage, not a new schema."""
        return self.model_dump()


class OpenCodeConfig(BaseModel):
    """Project admitted broker inputs into the existing native configuration.

    Ordinary serialization excludes the broker capability. Only ``to_config``
    unwraps it for the private controller configuration file; never log that
    projection or place it in a graph, public record or diagnostic.
    """

    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)

    permissions: dict[str, PermissionAction | dict[str, PermissionAction]] = Field(
        description="Native tool and skill permissions admitted for this controller."
    )
    broker_port: int = Field(
        ge=1,
        le=65535,
        description="Bound host broker TCP port reachable by this isolated controller.",
    )
    broker_token: SecretStr = Field(
        min_length=1,
        repr=False,
        exclude=True,
        description="Run-scoped broker capability, excluded from normal representations.",
    )

    def to_config(self) -> dict[str, object]:
        """Return a fresh native payload for the privileged private file boundary.

        The returned bearer header is plaintext because the native controller
        requires it. Permission rules are copied so mutation of the projection
        cannot change the admitted model. This method performs no file or network I/O.
        """
        return {
            "$schema": CONFIG_SCHEMA_URL,
            "autoupdate": False,
            "share": "disabled",
            "plugin": [],
            "mcp": {
                "laomedo": {
                    "type": "remote",
                    "url": f"http://{BROKER_HOST}:{self.broker_port}/mcp",
                    "headers": {
                        "Authorization": "Bearer "
                        + self.broker_token.get_secret_value()
                    },
                    "oauth": False,
                }
            },
            "permission": deepcopy(self.permissions),
            "tools": {"*": False, "skill": True, "laomedo_exec": True},
        }
