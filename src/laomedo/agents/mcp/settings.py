"""Single-owner protocol limits for external MCP access."""

from ipaddress import ip_address
from pathlib import Path
import os
import time

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SUPPORTED_LFX_VERSION = "1.12.3"
MAX_SCHEMA_BYTES = 131072
MAX_ARGUMENT_BYTES = 65536
MAX_RESULT_BYTES = 1048576
MAX_MANIFEST_BYTES = 32768
MAX_REGISTRATION_BYTES = 65536
CALL_TIMEOUT_SECONDS = 180


class McpSettings(BaseSettings):
    """Load shared local host configuration without graph-supplied overrides."""

    model_config = SettingsConfigDict(
        env_prefix="LAOMEDO_MCP_",
        env_file=None,
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )
    directory: Path | None = Field(
        default=None,
        description="Shared private rendezvous directory; absent uses user state.",
    )
    bind: str = Field(
        default="127.0.0.1",
        description="Loopback or explicit private IPv4 interface; never wildcard.",
    )
    controller_host: str = Field(
        default="host.docker.internal",
        description="Controller-visible host alias for this private interface.",
    )
    lease_seconds: int = Field(
        default=120,
        ge=30,
        le=3600,
        description="Inactive registration lifetime, renewed by supervising runner health.",
    )
    max_registrations: int = Field(
        default=64,
        ge=1,
        le=256,
        description="Maximum retained native tool registrations.",
    )
    max_calls: int = Field(
        default=8,
        ge=1,
        le=32,
        description="Maximum concurrent upstream calls per app process.",
    )

    @field_validator("bind")
    @classmethod
    def private_interface(cls, value):
        """Refuse unspecified, public and unsupported IPv6 listening addresses."""
        address = ip_address(value)
        if address.version != 4 or address.is_unspecified or not address.is_private:
            raise ValueError("mcp_private_interface_required")
        return value

    @field_validator("directory")
    @classmethod
    def absolute_directory(cls, value):
        """Require one unambiguous lexical directory shared by app and runner."""
        if value is not None and (
            not value.expanduser().is_absolute() or ".." in value.parts
        ):
            raise ValueError("mcp_private_state_unverified")
        return value

    @field_validator("controller_host")
    @classmethod
    def fixed_host(cls, value):
        """Permit only a host alias/address, never a URL or credential-bearing value."""
        if not value or any(
            c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-"
            for c in value
        ):
            raise ValueError("mcp_controller_host_invalid")
        return value

    def state_directory(self) -> Path:
        """Return the same point-of-use private location in app and runner processes."""
        return (
            (self.directory or Path.home().joinpath(".laomedo", "mcp"))
            .expanduser()
            .absolute()
        )

    def permission_policy(self):
        """Build a bounded trusted-system permission policy without ambient secrets."""
        if os.name != "nt":
            return None
        from laomedo.host.private_state.models import DirectoryPermissionPolicy
        from laomedo.host.private_state.windows import WindowsDirectorySecurity

        system = WindowsDirectorySecurity().system_directory()
        return DirectoryPermissionPolicy(
            whoami=system / "whoami.exe",
            icacls=system / "icacls.exe",
            environment={"SYSTEMROOT": str(system.parent)},
            deadline=time.monotonic() + 20,
        )


MCP_ERROR_CODES = frozenset(
    (
        "mcp_app_lifetime_required",
        "mcp_app_owner_conflict",
        "mcp_arguments_invalid",
        "mcp_arguments_too_large",
        "mcp_call_limit",
        "mcp_call_outcome_unknown",
        "mcp_connection_unavailable",
        "mcp_controller_host_invalid",
        "mcp_duplicate_tool",
        "mcp_event_loop_mismatch",
        "mcp_manifest_invalid",
        "mcp_manifest_too_large",
        "mcp_method_unsupported",
        "mcp_native_tool_unsupported",
        "mcp_native_version_unsupported",
        "mcp_private_interface_required",
        "mcp_private_state_unverified",
        "mcp_protocol_invalid",
        "mcp_provider_unsupported",
        "mcp_registration_failed",
        "mcp_registration_expired",
        "mcp_registration_limit",
        "mcp_registration_required",
        "mcp_registration_too_late",
        "mcp_registration_unavailable",
        "mcp_registration_unclaimed",
        "mcp_request_too_large",
        "mcp_result_too_large",
        "mcp_resume_binding_mismatch",
        "mcp_run_already_bound",
        "mcp_run_binding_mismatch",
        "mcp_schema_too_large",
        "mcp_server_limit",
        "mcp_tool_approval_unsupported",
        "mcp_tool_binding_changed",
        "mcp_tool_limit",
        "mcp_tool_not_selected",
    )
)
