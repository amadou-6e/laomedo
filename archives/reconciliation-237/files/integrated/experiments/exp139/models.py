"""Typed SDK policy projections for the existing disposable Git experiment."""

from pathlib import Path
import json

from experiments.exp139.settings import PROFILE_OVERRIDES
from laomedo.agents.agents.codex.controller.models import CodexLaunch
from laomedo.agents.errors import RunnerError
from pydantic import SecretStr


class GitMetadataLaunch(CodexLaunch):
    """Retain canonical run identity and add only the approved native arguments."""

    @classmethod
    def from_launch(cls, launch: CodexLaunch) -> "GitMetadataLaunch":
        """Copy canonical attributes without publicly serializing ownership secrets.

        Parameters
        ----------
        launch : CodexLaunch
            Host-selected policy, including its private lease ownership binding.

        Returns
        -------
        GitMetadataLaunch
            This policy subtype, preserving a more specific subtype when supplied.
        """
        return cls.model_validate(launch, from_attributes=True)

    def to_container_spec(self):
        """Add the original Git profile arguments to the normal SDK projection.

        Returns
        -------
        py_docker.containers.models.ContainerSpec
            Unchanged mounts and sandbox, with approved native command arguments.
        """
        spec = super().to_container_spec()
        if spec.command[-2:] != ["node", "/opt/acp/index.mjs"]:
            raise RunnerError("experiment_app_server_invocation_changed")
        environment = dict(spec.environment)
        environment["LAOMEDO_CODEX_ARGS"] = SecretStr(json.dumps(PROFILE_OVERRIDES))
        return spec.model_copy(update={"environment": environment})


class MailboxLaunch(GitMetadataLaunch):
    """Replace the trusted mediation client and bootstrap with the same relay."""

    def to_container_spec(self):
        """Project the experiment's relay without parsing a Docker CLI command.

        Returns
        -------
        py_docker.containers.models.ContainerSpec
            Original scoped mounts and identity plus the host-owned relay setup.
        """
        from py_docker.containers.models import Mount

        spec = super().to_container_spec()
        if self.capability is None:
            return spec
        client = Path(__file__).with_name("mailbox_client.mjs")
        relay = client.with_name("mailbox_relay.mjs")
        mounts = [
            (
                mount.model_copy(update={"source": str(client)})
                if mount.target == "/run/laomedo/mediate.mjs"
                else mount
            )
            for mount in spec.mounts
        ]
        mounts.append(
            Mount(
                type="bind",
                source=str(relay),
                target="/run/laomedo/relay.mjs",
                read_only=True,
            )
        )
        environment = dict(
            spec.environment,
            GIT_EXEC_PATH=SecretStr("/run/laomedo/bin"),
            LAOMEDO_MEDIATION_FILE_STDIO=SecretStr("1"),
        )
        command = list(spec.command)
        command[2] = (
            "cp /config.toml /home/runner/.codex/config.toml && "
            "node /run/laomedo/relay.mjs & relay=$!; "
            "for n in $(seq 1 100); do "
            "test -f /draft/.git/laomedo-mediation/ready && break; "
            'kill -0 "$relay" 2>/dev/null || exit 2; sleep 0.05; done; '
            "test -f /draft/.git/laomedo-mediation/ready || exit 2; "
            'exec "$@"'
        )
        return spec.model_copy(
            update={"mounts": mounts, "environment": environment, "command": command}
        )
