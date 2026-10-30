"""Validated runtime inputs for the private native OpenCode configuration."""

from copy import deepcopy
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from .settings import BROKER_HOST, CONFIG_SCHEMA_URL

PermissionAction = Literal["allow", "ask", "deny"]


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
