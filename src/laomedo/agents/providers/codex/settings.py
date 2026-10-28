"""Codex protocol/security pins and native feature configuration."""
import threading
import laomedo._paths as _package_paths

IMAGE = "laomedo-codex-boundary:0.159.2"


IMAGE_ID = "sha256:7b79ce12be47d6c8262dd4043895112d204416bda5cd891d124775df55587239"


GIT_IMAGE = "laomedo-codex-git:0.159.2"


GIT_IMAGE_ID = "sha256:eceda79a349c46a8afd6fb271e92b979f872ca67cbdf228fde6dee0856481e78"


CLI_VERSION = "codex-cli 0.159.2"
NATIVE_TURN_SECONDS = 180
NATIVE_RECEIPT_FILENAME = "container-receipt.json"


VOLUME = "laomedo-122-docker-auth"


SPLIT_TOOLS = frozenset(
    {
        "apply_patch",
        "clock__curr_time",
        "create_goal",
        "exec_command",
        "get_goal",
        "update_goal",
        "view_image",
        "wait_for_environment",
        "write_stdin",
    }
)


CONFIG = _package_paths.package_root() / "agents" / "providers" / "codex" / "resources" / "runner-config.toml"


SECCOMP = _package_paths.package_root() / "agents" / "providers" / "codex" / "resources" / "codex-seccomp.json"


SECCOMP_SHA256 = "b5dd6bafc529bb12e925a7fcef956a6d3c0f2f1b48f811ac030bb9cbebf50691"


MEDIATION_CLIENT = (
    _package_paths.package_root()
    / "agents"
    / "resources"
    / "mediation"
    / "agent_mediation_client.mjs"
)


CONFIG_SHA256 = "a14cd7e8abb4216b16d29e55809c2c3c9a9c33cc0196fd459fc033aaaa1ea4c4"


CONFIG_LF_SHA256 = "a1472e6d63ac71307af791767cc22fb76959549d9371114ff3382e4dfb3ad11b"


_CATALOG_INIT_LOCK = threading.Lock()


NATIVE_ERROR_KINDS = frozenset(
    {
        "contextWindowExceeded",
        "sessionBudgetExceeded",
        "usageLimitExceeded",
        "rateLimitExceeded",
        "flexUnavailable",
        "serverOverloaded",
        "cyberPolicy",
        "misalignmentPolicyViolation",
        "tooManyDenials",
        "internalServerError",
        "unauthorized",
        "badRequest",
        "threadRollbackFailed",
        "sandboxError",
        "other",
        "httpConnectionFailed",
        "responseStreamConnectionFailed",
        "responseStreamDisconnected",
        "responseTooManyFailedAttempts",
        "activeTurnNotSteerable",
    }
)


NATIVE_HTTP_ERROR_KINDS = frozenset(
    {
        "httpConnectionFailed",
        "responseStreamConnectionFailed",
        "responseStreamDisconnected",
        "responseTooManyFailedAttempts",
    }
)


from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Read at point of use; no cached environment, dotenv or credential contents.

    Strings preserve missing/empty values and exact ``== "1"`` flag behavior.
    Existing consumers own URL/path validation and stable public errors.
    """

    model_config = SettingsConfigDict(
        case_sensitive=True, env_file=None, secrets_dir=None,
        env_nested_delimiter=None, enable_decoding=False,
        extra="ignore", frozen=True, hide_input_in_errors=True,
    )

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings,
                                   dotenv_settings, file_secret_settings):
        """Only explicit arguments and the process environment supply settings."""
        return init_settings, env_settings

    multi_agent: str | None = Field(default=None, validation_alias='LAOMEDO_RUNNER_MULTI_AGENT', repr=False, exclude=True)
