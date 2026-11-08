"""Trusted provider registration values; never credentials or dynamic imports."""

from pydantic import BaseModel, ConfigDict, Field


class AgentProviderDescriptor(BaseModel):
    """Immutable host-selected identity and actual supported entrypoint capabilities."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    provider: str = Field(
        min_length=1, description="Registered provider ID admitted by host startup."
    )
    display_name: str = Field(min_length=1, description="Human-readable provider name.")
    managed_startup: bool = Field(
        description="Whether the managed runner service can start this provider."
    )
    join_bridge: bool = Field(
        description="Whether the existing supervised join bridge supports this provider."
    )
    output_requirements: bool = Field(
        description="Whether this provider implements the selected output-requirements protocol."
    )

    activity_provider: str = Field(
        min_length=1,
        description="Existing persisted Activity provider identifier, distinct from runtime selection ID.",
    )

    readiness_scope: str = Field(
        description="Exact native preflight guarantee, distinct from runtime health or isolation."
    )
