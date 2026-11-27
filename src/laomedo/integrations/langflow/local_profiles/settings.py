"""Fixed profile identity policy; no credentials or configurable auth bypasses."""

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SYSTEM_PROFILE_NAME = "__laomedo_system__"
PIN_DIGITS = 6
MAX_PROFILE_NAME_LENGTH = 40


class LocalProfileSettings(BaseSettings):
    """Explicit runtime location, without dotenv loading or credential fields."""

    model_config = SettingsConfigDict(
        env_file=None, secrets_dir=None, extra="ignore", frozen=True
    )

    runtime_root: Path = Field(
        validation_alias="LAOMEDO_LOCAL_PROFILE_RUNTIME",
        description="Explicit private runtime directory admitted before serving local profiles.",
    )
    provider_source: Path | None = Field(
        default=None,
        validation_alias="LAOMEDO_PROVIDER_SOURCE_WORKSPACE",
        description="Operator-selected source workspace for saved-connection execution; never a graph field.",
    )


PROFILE_COOKIE_NAMES = ("access_token_lf", "refresh_token_lf", "apikey_tkn_lflw")
