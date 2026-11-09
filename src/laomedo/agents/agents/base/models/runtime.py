"""Runtime values owned by the shared Agent capability."""

from collections.abc import Callable
from laomedo.agents.agents.base.resources import (
    ContainerBuilder,
    OwnedResourceBuilder,
)
from laomedo.agents.agents.base.models.credentials import CredentialBinding
from laomedo.agents.agents.base.models.failures import FailureObservation
from pathlib import Path
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    InstanceOf,
    JsonValue,
    SkipValidation,
    model_validator,
)
from typing import Literal


class RuntimeBinding(BaseModel):
    """Immutable runtime identity projected into the existing retained run schema."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    provider: str = Field(description="Trusted provider identifier for this run.")
    profile: str | None = Field(
        description="Safe local runtime profile identifier, if applicable."
    )
    image: str | None = Field(
        description="Configured human-readable runtime image name."
    )
    image_id: str | None = Field(
        description="Verified immutable runtime image identity."
    )
    execution_mode: str = Field(
        description="Existing persisted execution-mode identifier."
    )
    cli_version: str | None = Field(
        description="Observed or pinned native CLI version."
    )
    config_sha256: str | None = Field(
        description="Admitted configuration digest, if required."
    )
    credential: CredentialBinding | None = Field(
        default=None,
        repr=False,
        description="Public authentication identity/outcome only.",
    )

    def record_fields(self):
        """Preserve the external record key set; credential contains public identity metadata only."""
        return self.model_dump(exclude={"provider"})


class RuntimeObservation(BaseModel):
    """Separate launch, readiness and native identity observations for one scope."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    provider: str = Field(
        description="Registered native provider for the observed scope."
    )
    launched: bool = Field(
        description="Whether this runtime allocated its owned process/session scope."
    )
    ready: bool | None = Field(
        description="Observed protocol readiness; None means not yet established."
    )
    native_session: str | None = Field(
        default=None,
        description="Observed native session ID, never fabricated from a Laomedo run ID.",
    )


class CancellationObservation(BaseModel):
    """Cancellation admission is distinct from native interruption confirmation."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    requested: bool = Field(
        description="Whether interruption was requested for owned active work."
    )
    confirmed: bool | None = Field(
        description="Observed interruption acknowledgement; unknown is not false or success."
    )


class CleanupObservation(BaseModel):
    """Exact resource cleanup result, never a global process-health assertion."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    confirmed: bool | None = Field(
        description="Whether all resources owned by the selected scope are confirmed closed."
    )
    scope: str = Field(
        min_length=1,
        description="Resource set to which this cleanup observation applies.",
    )


class RuntimeLaunch(BaseModel):
    """Host-only owned runtime handle and its separate launch/readiness evidence."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    runtime: SkipValidation[object] = Field(
        exclude=True,
        repr=False,
        description="Opaque host-owned runtime; never serialized or supplied by graph input.",
    )
    observation: RuntimeObservation = Field(
        description="Actual launch and readiness facts at construction, not execution success."
    )


class ReadinessObservation(BaseModel):
    """A scoped readiness result, independent of process health and isolation."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    provider: str = Field(
        description="Registered provider whose preflight was observed."
    )
    ready: bool | None = Field(
        description="Native ready/blocked result; configuration-only evidence remains unknown."
    )
    scope: str = Field(
        description="Exact native/authentication/configuration check established by this result."
    )
    payload: SkipValidation[dict[str, JsonValue]] = Field(
        repr=False,
        description="Existing public preflight payload without schema or native-extension changes.",
    )


class ProcessHealthObservation(BaseModel):
    """Liveness of a named resource set, never permission or authentication proof."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    alive: bool | None = Field(
        description="Observed process/transport liveness; unknown is not healthy."
    )
    scope: str = Field(description="Exact checked process or resource set.")


class IsolationObservation(BaseModel):
    """Independent sandbox observation, not inferred from readiness or liveness."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    verified: bool | None = Field(
        description="Whether the stated isolation gate was actually established."
    )
    scope: str = Field(description="Exact sandbox policy/resource boundary checked.")


class ResourceBinding(BaseModel):
    """Typed dependency identity; native subclasses add their named launch inputs."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    resource_id: str = Field(
        min_length=1, description="Unique admitted resource-plan step identity."
    )


class ResourceStep(BaseModel):
    """Common trusted topology metadata; native allocation is not a builder hook."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        hide_input_in_errors=True,
        arbitrary_types_allowed=True,
    )
    id: str = Field(min_length=1, description="Unique resource step identity.")
    depends_on: tuple[str, ...] = Field(
        default=(), description="Earlier required step identities."
    )
    phase: Literal["prepare", "launch"] = Field(
        description="Dependency versus controller phase."
    )
    quiesce: Callable[[], None] | None = Field(
        default=None,
        exclude=True,
        repr=False,
        description="Optional native pre-close stop; currently OpenCode workers only.",
    )


class ContainerStep(ResourceStep):
    """Builder returns ContainerSession; shared runtime opens and closes Docker."""

    build: InstanceOf[ContainerBuilder] = Field(
        exclude=True,
        repr=False,
        description="Trusted spec builder, not a native allocation callback.",
    )
    controller: bool = Field(
        default=False, description="This is the scope's single ACP controller."
    )
    stop_when: Callable[[], bool] | None = Field(
        default=None,
        exclude=True,
        repr=False,
        description="Optional controller monitor, never allowed on another resource.",
    )


class OwnedResourceStep(ResourceStep):
    """Owned non-Docker service such as a broker or telemetry receiver."""

    build: InstanceOf[OwnedResourceBuilder] = Field(
        exclude=True,
        repr=False,
        description="Trusted non-Docker resource allocation under shared rollback.",
    )


class ResourcePlan(BaseModel):
    """Provider topology; shared runtime owns allocation, rollback and closure."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    steps: tuple[ContainerStep | OwnedResourceStep, ...] = Field(
        description="Dependency-ordered host resource steps."
    )

    @model_validator(mode="after")
    def validate_dependencies(self):
        """Reject duplicate, missing/forward and cross-phase dependencies before allocation."""
        seen = set()
        launching = False
        controllers = 0
        for step in self.steps:
            if step.id in seen or not set(step.depends_on) <= seen:
                raise ValueError("invalid_resource_dependencies")
            launching = launching or step.phase == "launch"
            if launching and step.phase == "prepare":
                raise ValueError("invalid_resource_phase_order")
            if isinstance(step, ContainerStep):
                if step.controller:
                    controllers += 1
                    if step.phase != "launch":
                        raise ValueError("controller_requires_launch_phase")
                elif step.stop_when is not None:
                    raise ValueError("monitor_requires_controller")
            seen.add(step.id)
        if controllers != 1:
            raise ValueError("one_controller_required")
        return self


class RuntimeLaunchRequest(BaseModel):
    """Admitted scope inputs; provider subclasses add named host launch configuration."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    provider: str = Field(
        min_length=1, description="Trusted registered provider identity."
    )
    scope_id: str = Field(min_length=1, description="Exact single-use scope identity.")
    workspace: Path = Field(repr=False, description="Admitted mounted workspace.")
    evidence: Path = Field(
        repr=False, description="Private receipts and native evidence directory."
    )
    deadline: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Admitted native scope lifetime bound when supplied; not a new attempt deadline.",
    )


class NamedCleanup(BaseModel):
    """Cleanup fact for one named owned resource."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    resource_id: str = Field(min_length=1, description="Resource-plan step identity.")
    observation: CleanupObservation = Field(
        description="Exact cleanup fact; uncertainty is retained."
    )


class RuntimeCleanupReport(BaseModel):
    """Controller and resource cleanup facts, independent of attempt success."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    controller: CleanupObservation | None = Field(
        default=None, description="Controller cleanup, or None when never allocated."
    )
    resources: tuple[NamedCleanup, ...] = Field(
        description="Other allocated resource observations."
    )
    primary: FailureObservation | None = Field(
        default=None, description="Safe original failure evidence."
    )
    code: str | None = Field(
        default=None, description="Existing provider boundary failure code."
    )

    @property
    def confirmed(self) -> bool:
        """Only explicit confirmation of every named scope establishes cleanup."""
        return (
            self.code is None
            and (self.controller is None or self.controller.confirmed is True)
            and all(item.observation.confirmed is True for item in self.resources)
        )
