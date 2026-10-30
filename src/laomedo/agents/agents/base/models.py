"""Public provider binding carried as one strict internal lifecycle value."""
from pydantic import BaseModel, ConfigDict, Field


class CredentialBinding(BaseModel):
    """Public authentication identity/outcome metadata, never login material."""
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)
    credential_mode: str = Field(description="Authentication mode selected by trusted host startup.")
    credential_ref: str | None = Field(description="Safe connection identity, never login material.")
    auth_outcome: str = Field(description="Observed authentication admission outcome.")


class RuntimeBinding(BaseModel):
    """Immutable runtime identity projected into the existing retained run schema."""
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)
    provider: str = Field(description="Trusted provider identifier for this run.")
    profile: str | None = Field(description="Safe local runtime profile identifier, if applicable.")
    image: str | None = Field(description="Configured human-readable runtime image name.")
    image_id: str | None = Field(description="Verified immutable runtime image identity.")
    execution_mode: str = Field(description="Existing persisted execution-mode identifier.")
    cli_version: str | None = Field(description="Observed or pinned native CLI version.")
    config_sha256: str | None = Field(description="Admitted configuration digest, if required.")
    credential: CredentialBinding | None = Field(
        default=None, repr=False, description="Public authentication identity/outcome only."
    )

    def record_fields(self):
        """Preserve the external record key set; credential contains public identity metadata only."""
        return self.model_dump(exclude={"provider"})
