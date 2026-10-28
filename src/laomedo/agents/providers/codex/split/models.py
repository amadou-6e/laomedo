"""Codex policy for a credential-bearing controller and isolated tool executor."""

from pydantic import Field, SecretStr

from laomedo.agents.providers.codex.native.models import CodexLaunch


class SplitLaunch(CodexLaunch):
    """Extend canonical launch policy without another Docker command builder."""

    executor_id: str = Field(
        description="Observed immutable executor ID whose network the controller joins."
    )
    provider_config: tuple[str, ...] = Field(
        default=(), description="Host-approved native provider configuration overrides."
    )
    access_token: SecretStr | None = Field(
        default=None,
        repr=False,
        exclude=True,
        description="Launch-only controller OAuth credential; never sent to executor or Docker control environment.",
    )

    def to_container_spec(self):
        """Project the controller's unchanged deferred-execution policy."""
        spec = super().to_container_spec()
        command = list(spec.command)
        command[-2:-2] = [
            "-c",
            "features.deferred_executor=true",
            "-c",
            "features.executor_capability_discovery=true",
        ]
        for setting in self.provider_config:
            command[-2:-2] = ["-c", setting]
        environment = dict(spec.environment)
        if self.access_token is not None:
            environment["ACCESS_TOKEN"] = self.access_token
        return spec.model_copy(
            update={
                "command": command,
                "environment": environment,
                "network_mode": "container:" + self.executor_id,
                "security_opt": ["no-new-privileges"],
            }
        )
