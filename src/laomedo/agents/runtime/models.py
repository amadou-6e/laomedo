"""Public provider binding carried as one strict internal lifecycle value."""
from pydantic import BaseModel, ConfigDict, Field


class RuntimeBinding(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", hide_input_in_errors=True)
    provider: str
    profile: str | None
    image: str | None
    image_id: str | None
    execution_mode: str
    cli_version: str | None
    config_sha256: str | None
    credential: dict | None = Field(default=None, repr=False)

    def record_fields(self):
        """Preserve the external record key set; credential contains public identity metadata only."""
        return self.model_dump(exclude={"provider"})
