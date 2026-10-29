"""Canonical application policy for one Codex controller launch."""

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from laomedo.agents.providers.codex import settings
from laomedo.agents.runtime.errors import RunnerError
from laomedo.host.leases import settings as lease_settings

if TYPE_CHECKING:
    from py_docker.containers.models import ContainerSpec


class CodexLaunch(BaseModel):
    """Group run identity, application mounts and mediated execution scope."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    workspace: Path = Field(description="Prepared writable execution workspace.")
    canonical: Path = Field(
        description="Read-only canonical snapshot for integrity checks."
    )
    store_mount: Path = Field(description="Prepared run-local skill store mount.")
    image: str = Field(description="Host-authorized immutable Codex image ID.")
    profile: str = Field(
        default_factory=lambda: settings.VOLUME,
        description="Dedicated named credential volume selected by the host runner.",
    )
    name: str = Field(
        default_factory=lambda: "laomedo-codex-" + uuid4().hex,
        description="Unique controller name also recorded by lease supervision.",
    )
    run_id: str | None = Field(
        default=None,
        description="Application run identity bound to the independent lease.",
    )
    launch_token: SecretStr | None = Field(
        default=None,
        repr=False,
        exclude=True,
        description="Private lease ownership token; never serialize publicly.",
    )
    capability: Path | None = Field(
        default=None,
        repr=False,
        exclude=True,
        description="Read-only host grant file for mediated operations.",
    )
    mediator_url: str | None = Field(
        default=None,
        description="Host-owned mediation route, never a provider credential.",
    )
    mediator_instance: str | None = Field(
        default=None, description="Expected mediation service instance."
    )
    command_directory: Path | None = Field(
        default=None, description="Prepared read-only mediated command shims."
    )
    repository: str | None = Field(
        default=None, description="Authorized repository for mediated Git operations."
    )
    branch: str | None = Field(default=None, description="Authorized execution branch.")
    base_branch: str = Field(
        default="main", description="Authorized pull-request base branch."
    )
    config: Path = Field(
        default_factory=lambda: settings.CONFIG,
        description="Reviewed Codex configuration mounted read-only.",
    )
    seccomp: Path = Field(
        default_factory=lambda: settings.SECCOMP,
        description="Reviewed seccomp policy bytes supplied inline to the SDK.",
    )
    seccomp_sha256: str = Field(
        default_factory=lambda: settings.SECCOMP_SHA256,
        description="Required checksum of the exact seccomp bytes sent to Docker.",
    )

    def to_container_spec(self) -> "ContainerSpec":
        """Project application policy into the optional generic Docker contract.

        Returns
        -------
        py_docker.containers.models.ContainerSpec
            Exact normal-mode launch policy; no CLI argument parsing or fallback.

        Raises
        ------
        RunnerError
            The reviewed seccomp or mediation scope is incomplete or altered.
        """
        from py_docker.containers.models import ContainerSpec, Mount

        policy = self.seccomp.read_bytes()
        if hashlib.sha256(policy).hexdigest() != self.seccomp_sha256:
            raise RunnerError("seccomp_profile_changed")
        mounts = [
            Mount(type="volume", source=self.profile, target="/home/runner/.codex"),
            Mount(type="bind", source=str(self.workspace), target="/draft"),
            Mount(
                type="bind",
                source=str(self.canonical),
                target="/canonical",
                read_only=True,
            ),
            Mount(type="bind", source=str(self.store_mount), target="/store"),
            Mount(
                type="bind",
                source=str(self.config),
                target="/config.toml",
                read_only=True,
            ),
        ]
        environment = {
            "CODEX_CONFIG": '{"features":{"apps":false,"plugins":false,"memories":false},"apps":{"_default":{"enabled":false}}}',
        }
        mediated = all(
            value is not None
            for value in (self.capability, self.mediator_url, self.mediator_instance)
        )
        if (
            any(
                value is not None
                for value in (
                    self.capability,
                    self.mediator_url,
                    self.mediator_instance,
                )
            )
            and not mediated
        ):
            raise RunnerError("incomplete_mediator_mount")
        if mediated:
            mounts.extend(
                [
                    Mount(
                        type="bind",
                        source=str(self.capability),
                        target="/run/laomedo/capability",
                        read_only=True,
                    ),
                    Mount(
                        type="bind",
                        source=str(settings.MEDIATION_CLIENT),
                        target="/run/laomedo/mediate.mjs",
                        read_only=True,
                    ),
                ]
            )
            environment.update(
                LAOMEDO_MEDIATOR_URL=self.mediator_url,
                LAOMEDO_MEDIATOR_INSTANCE=self.mediator_instance,
                LAOMEDO_CAPABILITY_FILE="/run/laomedo/capability",
            )
        if self.command_directory is not None:
            if not mediated or self.repository is None or self.branch is None:
                raise RunnerError("incomplete_command_mount")
            mounts.extend(
                [
                    Mount(
                        type="bind",
                        source=str(self.command_directory),
                        target="/run/laomedo/bin",
                        read_only=True,
                    ),
                    Mount(
                        type="bind",
                        source=str(
                            settings.MEDIATION_CLIENT.with_name("agent_gh_adapter.mjs")
                        ),
                        target="/run/laomedo/gh.mjs",
                        read_only=True,
                    ),
                    Mount(
                        type="bind",
                        source=str(
                            settings.MEDIATION_CLIENT.with_name("agent_git_remote.mjs")
                        ),
                        target="/run/laomedo/git-remote.mjs",
                        read_only=True,
                    ),
                ]
            )
            environment.update(
                LAOMEDO_REPOSITORY=self.repository,
                LAOMEDO_RUN_BRANCH=self.branch,
                LAOMEDO_BASE_BRANCH=self.base_branch,
                PATH="/run/laomedo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            )
        if self.image in {settings.GIT_IMAGE, settings.GIT_IMAGE_ID}:
            environment.update(
                GIT_CONFIG_COUNT="1",
                GIT_CONFIG_KEY_0="safe.directory",
                GIT_CONFIG_VALUE_0="/draft",
            )
        labels = {}
        if self.run_id and self.launch_token:
            labels = {
                lease_settings.LABEL_RUN: self.run_id,
                lease_settings.LABEL_TOKEN: self.launch_token,
            }
        return ContainerSpec(
            image=self.image,
            name=self.name,
            command=[
                "sh",
                "-c",
                'cp /config.toml /home/runner/.codex/config.toml && exec "$@"',
                "bootstrap",
                "node",
                "/opt/acp/index.mjs",
            ],
            user="10001:10001",
            working_dir="/draft",
            environment=environment,
            labels=labels,
            mounts=mounts,
            network_mode="bridge",
            read_only=False,
            stdin_open=True,
            tmpfs={
                "/home/runner/.codex/skills": "ro,mode=0555",
                "/home/runner/.codex/plugins": "ro,mode=0555",
                "/home/runner/.agents": "ro,mode=0555",
            },
            security_opt=["no-new-privileges", "seccomp=" + policy.decode("utf-8")],
        )


class SplitPolicy(BaseModel):
    """Host-only provider configuration for a credential-free tool executor."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    provider_config: tuple[str, ...] = ()
    access_token: SecretStr | None = Field(default=None, repr=False, exclude=True)


class CodexTurn(BaseModel):
    """Native terminal identity retained across the common ACP lifecycle."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    turn_id: str
    status: str
    error: str | None = None
