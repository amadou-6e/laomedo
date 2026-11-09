"""Shared provider bindings and private allowlisted failure observations."""

from pydantic import BaseModel, ConfigDict, Field
from pydantic import JsonValue, SkipValidation, SecretStr, InstanceOf
from pydantic import model_validator
from typing import ClassVar, Literal
import hashlib
from laomedo.agents.artifacts.models import ArtifactReference
from laomedo.agents.interface.models import PrecheckEvidence
from laomedo.agents.orchestration.models import HandoffProvenance
from laomedo.agents.agents.base.settings import SDK_FAILURE_CODES
from laomedo.agents.agents.base.settings import SDK_FAILURE_OPERATIONS
from laomedo.agents.agents.base.settings import RUNNER_FAILURE_CODES
from pathlib import Path
from collections.abc import Callable
from laomedo.agents.agents.base.contracts import (
    BasePostFreezeSettlement,
    ContainerBuilder,
    OwnedResourceBuilder,
)


class CredentialBinding(BaseModel):
    """Public authentication identity/outcome metadata, never login material."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    credential_mode: str = Field(
        description="Authentication mode selected by trusted host startup."
    )
    credential_ref: str | None = Field(
        description="Safe connection identity, never login material."
    )
    auth_outcome: str = Field(description="Observed authentication admission outcome.")


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


class PreparedWorkspaceState(BaseModel):
    """Related working-state bindings observed before any native execution."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    source_hash: str = Field(description="Verified canonical source inventory hash.")
    effective_hash: str = Field(
        description="Working inventory after pinned skills and artifact imports."
    )
    git: bool = Field(
        description="Whether preparation preserved an isolated Git baseline."
    )
    baseline: str | None = Field(
        description="Observed Git commit, null for a file-only workspace."
    )

    def record_fields(self) -> dict:
        """Project the existing flat workspace keys without changing scope vocabulary."""
        return dict(
            source_hash=self.source_hash,
            effective_hash=self.effective_hash,
            workspace_mode="git" if self.git else "files",
            git_baseline=self.baseline,
            post_run_hash_scope="working_files_only" if self.git else "all_files",
        )


class AgentSkillBinding(BaseModel):
    """Installed skill identity and immutable byte evidence for a new run."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    skill_id: str = Field(description="Admitted materialized skill name.")
    revision_id: str = Field(description="Pinned registry byte revision.")
    tree_hash: str = Field(description="Verified immutable installed skill inventory.")
    file_hashes: dict[str, str] = Field(
        description="Path-indexed verified installed file hashes."
    )
    delivery_mode: Literal["project_discovery"] = Field(
        description="Existing run-local skill discovery mechanism."
    )
    use_evidence: Literal["offered"] = Field(
        description="Preparation offers a skill; it does not claim native use."
    )


class SkillGitExclusion(BaseModel):
    """Run-local exclusion evidence; absence of Git omits rule/digest keys."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    enabled: bool = Field(description="Whether owned Git exclusion metadata exists.")
    rules: list[str] | None = Field(
        default=None, description="Installed exclusion rules, omitted when disabled."
    )
    exclude_sha256: str | None = Field(
        default=None,
        description="Exact exclusion-file byte digest, omitted when disabled.",
    )


class AgentGitHubScope(BaseModel):
    """Host-authority response binding; this record itself does not grant access."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    invocation_id: str = Field(description="Host authorization invocation identity.")
    repository: str = Field(description="Host-authorized owner/repository.")
    branch: str = Field(description="Host-authorized working branch.")
    base_branch: str | None = Field(
        default=None,
        description="Host-authorized PR/fetch target, omitted when not needed.",
    )


class PreparedRunRecord(BaseModel):
    """New durable run construction, not a schema for later lifecycle reads."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    RECORD_KEYS: ClassVar[tuple[str, ...]] = (
        "schema_version",
        "run_id",
        "status",
        "error_category",
        "source_hash",
        "workspace_mode",
        "git_baseline",
        "post_run_hash_scope",
        "effective_hash",
        "post_run_hash",
        "input_hash",
        "skill",
        "skills",
        "skill_git_exclusion",
        "provider",
        "handoff",
        "imported_artifacts",
        "requested_model",
        "requested_effort",
        "effective_model",
        "effective_effort",
        "profile",
        "image",
        "image_id",
        "execution_mode",
        "cli_version",
        "config_sha256",
        "credential",
        "thread_id",
        "runner_instance_id",
        "turns",
        "answer",
        "output_ref",
        "raw_event_ref",
        "client_request_id",
        "activity_initial_attempt_id",
        "output_requirements",
        "requirements_revision",
        "output_retries",
        "precheck",
        "request_hash",
        "cancel_requested",
        "cancel_confirmed",
        "github_scope",
    )
    run_id: str = Field(description="New canonical runner run UUID.")
    workspace: PreparedWorkspaceState = Field(
        description="Related observed working-state bindings."
    )
    runtime: RuntimeBinding = Field(
        description="Canonical admitted provider/runtime binding."
    )
    skills: list[AgentSkillBinding] = Field(
        description="Pinned installed skills in request order."
    )
    skill_git_exclusion: SkillGitExclusion = Field(
        description="Exact run-local skill exclusion evidence."
    )
    handoff: HandoffProvenance | None = Field(
        description="Admitted source provenance, explicitly null when absent."
    )
    imported_artifacts: list[ArtifactReference] = Field(
        description="Admitted verified input files."
    )
    requested_model: str = Field(description="Admitted native model choice.")
    requested_effort: str = Field(description="Admitted native reasoning effort.")
    runner_instance_id: str = Field(description="Owning host runner instance.")
    client_request_id: str | None = Field(
        description="Existing async request identity or explicit null."
    )
    activity_initial_attempt_id: str = Field(
        description="New initial capture correlation UUID."
    )
    output_requirements: dict[str, JsonValue] | None = Field(
        description="Existing validated, content-addressed downstream schema; canonical verifier retains ownership."
    )
    output_retries: int = Field(
        description="Existing admitted correction count; no new experiment limit."
    )
    request_hash: str | None = Field(
        description="Existing canonical request identity or explicit null."
    )
    github_scope: AgentGitHubScope | None = Field(
        description="Optional host authorization binding; absent on disk when null."
    )
    input_hash: str = Field(
        description="Canonical digest of the exact admitted task bytes."
    )

    @classmethod
    def for_preparation(cls, *, task: str, **values) -> "PreparedRunRecord":
        """Bind admitted task bytes to the grouped preparation inputs without effects."""
        return cls(
            input_hash="sha256:" + hashlib.sha256(task.encode()).hexdigest(), **values
        )

    def to_record(self) -> dict:
        """Preserve the flat initial JSON schema, defaults, nulls and optional scope."""
        value = self.model_dump(exclude={"workspace", "runtime", "github_scope"})
        value.update(self.workspace.record_fields())
        value.update(self.runtime.record_fields())
        value.update(
            schema_version=1,
            status="prepared",
            error_category=None,
            post_run_hash=None,
            skill=value["skills"][0] if len(self.skills) == 1 else None,
            provider=self.runtime.provider,
            effective_model=None,
            effective_effort=None,
            thread_id=None,
            turns=[],
            answer=None,
            output_ref=None,
            raw_event_ref=f"laomedo:run:{self.run_id}:events",
            requirements_revision=(self.output_requirements or {}).get(
                "requirements_revision"
            ),
            precheck=PrecheckEvidence(installed=False, call_count=0).model_dump(),
            cancel_requested=False,
            cancel_confirmed=False,
        )
        value["skill_git_exclusion"] = self.skill_git_exclusion.model_dump(
            exclude_unset=True
        )
        if self.github_scope is not None:
            value["github_scope"] = self.github_scope.model_dump(exclude_unset=True)
        expected = set(self.RECORD_KEYS) - (
            {"github_scope"} if self.github_scope is None else set()
        )
        assert (
            set(value) == expected
        ), "Prepared record keys must explicitly match the persistence contract."
        return {key: value[key] for key in self.RECORD_KEYS if key in value}


class FailureObservation(BaseModel):
    """Allowlisted diagnostic scalars, never an exception or private SDK receipt."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    stage: Literal[
        "startup", "execution", "terminal", "cleanup", "snapshot", "lease_finish"
    ] = Field(description="Trusted lifecycle stage at observation.")
    code: str | None = Field(
        default=None,
        description="Known fixed runner category; unknown/dynamic categories are omitted.",
    )
    sdk_class: str | None = Field(
        default=None, description="Exact trusted SDK exception class name."
    )
    sdk_code: str | None = Field(
        default=None, description="Validated class-level SDK machine code."
    )
    operation: str | None = Field(
        default=None, description="Known literal SDK operation, without external text."
    )
    primary_sdk_code: str | None = Field(
        default=None, description="One trusted SDK primary category masked by cleanup."
    )
    primary_operation: str | None = Field(
        default=None, description="Known literal operation of that one SDK primary."
    )

    @model_validator(mode="after")
    def validate_safe_values(self):
        """Reject direct construction that bypasses the explicit safe projection."""
        if self.code is not None and self.code not in RUNNER_FAILURE_CODES:
            raise ValueError("unsafe_failure_code")
        if (
            self.sdk_class is not None
            and SDK_FAILURE_CODES.get(self.sdk_class) != self.sdk_code
        ):
            raise ValueError("unsafe_sdk_failure_class")
        if (
            self.sdk_code is not None
            and self.sdk_code not in SDK_FAILURE_CODES.values()
        ):
            raise ValueError("unsafe_sdk_failure_code")
        if (
            self.primary_sdk_code is not None
            and self.primary_sdk_code not in SDK_FAILURE_CODES.values()
        ):
            raise ValueError("unsafe_sdk_primary_code")
        if any(
            value is not None and value not in SDK_FAILURE_OPERATIONS
            for value in (self.operation, self.primary_operation)
        ):
            raise ValueError("unsafe_sdk_operation")
        return self

    @classmethod
    def from_values(
        cls,
        *,
        stage,
        code=None,
        sdk_class=None,
        sdk_code=None,
        operation=None,
        primary_sdk_code=None,
        primary_operation=None,
    ):
        """Omit unknown candidates rather than sanitize arbitrary external text."""
        trusted = (
            type(sdk_class) is str and SDK_FAILURE_CODES.get(sdk_class) == sdk_code
        )
        return cls(
            stage=stage,
            code=code if type(code) is str and code in RUNNER_FAILURE_CODES else None,
            sdk_class=sdk_class if trusted else None,
            sdk_code=sdk_code if trusted else None,
            operation=(
                operation
                if trusted
                and type(operation) is str
                and operation in SDK_FAILURE_OPERATIONS
                else None
            ),
            primary_sdk_code=(
                primary_sdk_code
                if trusted
                and type(primary_sdk_code) is str
                and primary_sdk_code in SDK_FAILURE_CODES.values()
                else None
            ),
            primary_operation=(
                primary_operation
                if trusted
                and type(primary_operation) is str
                and primary_operation in SDK_FAILURE_OPERATIONS
                else None
            ),
        )


class AttemptFailureRecord(BaseModel):
    """Private final failure snapshot; cleanup truth never accepts the run."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    primary: FailureObservation = Field(
        description="First safe failure; terminal cancellation is attributed to supervision only when no earlier failure exists."
    )
    cleanup: FailureObservation | None = Field(
        default=None, description="Observed secondary finalization failure, if any."
    )
    final_category: str | None = Field(
        description="Allowlisted existing final category; public routing remains authoritative."
    )
    cleanup_source: Literal["lease_result", "opencode_owned_resources"] | None = Field(
        default=None,
        description="Domain of the observed cleanup fact, not global cleanup.",
    )
    cleanup_verified: bool | None = Field(
        default=None,
        description="Actual cleanup verdict in that domain; null means unavailable.",
    )

    @model_validator(mode="after")
    def validate_cleanup_fact(self):
        """Keep unavailable observations distinct from a negative verdict."""
        if (self.cleanup_source is None) != (self.cleanup_verified is None):
            raise ValueError("cleanup_source_required")
        if (
            self.final_category is not None
            and self.final_category not in RUNNER_FAILURE_CODES
        ):
            raise ValueError("unsafe_failure_code")
        return self

    def to_record(self):
        """Serialize only the declared safe private snapshot fields."""
        return self.model_dump()


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


class CommandRequest(BaseModel):
    """One admitted workspace command; no credential or executable selection authority."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    command: str | None = Field(
        default=None,
        min_length=1,
        repr=False,
        description="Command text to admit under provider-local workspace policy.",
    )
    deadline: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Absolute host monotonic deadline; None retains provider's bounded default.",
    )

    argv: list[str] | None = Field(
        default=None,
        min_length=1,
        repr=False,
        description="Exact admitted native argv for fixed probes; mutually exclusive with shell text.",
    )

    @model_validator(mode="after")
    def validate_command_form(self):
        """Admit one explicit command representation without shell coercion."""
        if (self.command is None) == (self.argv is None):
            raise ValueError("one_command_form_required")
        return self


class CommandResult(BaseModel):
    """Native command outcome plus independently observed resource cleanup."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    exit_code: int = Field(
        description="Native exit status, including provider's established timeout/cancellation mapping."
    )
    stdout: str = Field(
        default="",
        repr=False,
        description="Bounded decoded standard output; not diagnostic authorization evidence.",
    )
    stderr: str = Field(
        default="",
        repr=False,
        description="Bounded decoded standard error when the provider exposes separate streams.",
    )
    cleanup: CleanupObservation = Field(
        description="Cleanup evidence for resources allocated by this command."
    )


class CredentialRequest(BaseModel):
    """Provider-local credential admission constraints, with no secret material."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    minimum_validity_seconds: float | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
        description="Required remaining validity when native policy can establish it.",
    )
    deadline: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Absolute monotonic deadline for credential preparation.",
    )

    timeout_seconds: float = Field(
        default=20.0,
        gt=0,
        allow_inf_nan=False,
        description="Native credential-check timeout ceiling, separately clamped to the request deadline.",
    )


class CredentialMaterial(BaseModel):
    """Private host transfer of one credential and its existing public identity."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    token: SecretStr | None = Field(
        default=None,
        exclude=True,
        repr=False,
        description="Borrowed native credential; only explicit host projection may unwrap it.",
    )
    identity: dict[str, JsonValue] | None = Field(
        default=None,
        repr=False,
        description="Existing nonsecret connection metadata, never raw login state.",
    )
    binding: CredentialBinding = Field(
        description="Public preparation/identity outcome with no credential material."
    )

    def native_pair(self):
        """Unwrap only at the existing host launch boundary, preserving native identity."""
        return (
            self.token.get_secret_value() if self.token is not None else None
        ), self.identity


class ModelChoice(BaseModel):
    """A native model identifier and its actually advertised reasoning choices."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="allow", hide_input_in_errors=True
    )
    id: str = Field(
        min_length=1,
        description="Native model identifier, not a display label or implicit selection.",
    )
    efforts: list[str] = Field(
        default_factory=list,
        description="Native supported effort identifiers; an empty list does not invent a default.",
    )


class ModelCatalogSnapshot(BaseModel):
    """Validated choices with unchanged provider metadata at the wire boundary."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="allow", hide_input_in_errors=True
    )
    models: list[ModelChoice] = Field(
        description="Native discovery choices without submitting a model turn."
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


class JournalEntry(BaseModel):
    """Common journal identity; operation subclasses constrain shared fields."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    attempt_id: str = Field(
        min_length=1, description="Owning admitted attempt identity."
    )
    extensions: dict[str, JsonValue] = Field(
        default_factory=dict,
        repr=False,
        description="Detached provider-native metadata, not shared record updates.",
    )

    @model_validator(mode="after")
    def reject_shared_updates(self):
        """Native extensions cannot override shared state or operation fields."""
        reserved = {
            "status",
            "cancel_requested",
            "cancel_confirmed",
            "snapshot_ready",
            "post_run_hash",
            "output_ref",
            "error_category",
        }
        if (reserved | set(type(self).model_fields)) & self.extensions.keys():
            raise ValueError("reserved_journal_extension")
        return self


class OwnershipEntry(JournalEntry):
    """Persist exact ownership before native allocation."""

    name: str = Field(min_length=1, description="Exact admitted container name.")
    docker_endpoint: str = Field(min_length=1, description="Pinned owning daemon.")
    token: SecretStr = Field(
        exclude=True,
        repr=False,
        description="Host ownership token, explicitly projected privately.",
    )
    receipt: Path | None = Field(
        default=None, repr=False, description="Private native receipt when admitted."
    )


class NativeSessionEntry(JournalEntry):
    """Bind a real conversation before dispatch; never a host placeholder."""

    native_session: str = Field(
        min_length=1, description="Actual native conversation identity."
    )
    communication_protocol: str = Field(
        description="Observed native communication protocol."
    )


class DispatchEntry(JournalEntry):
    """Reserve or mark one exact host turn."""

    turn_id: str = Field(
        min_length=1, description="Reserved host/native turn identity."
    )


class TurnEntry(JournalEntry):
    """Native turn facts; provider-specific receipt fields remain extensions."""

    turn_id: str = Field(min_length=1, description="Observed native turn identity.")
    status: str = Field(
        description="Original native turn status, not run-state mutation."
    )


class LeaseEntry(JournalEntry):
    """Bind supervision and grant identity without transporting a live lease."""

    lease_instance: str = Field(description="Admitted supervisor instance identity.")
    grant_id: str | None = Field(
        description="Native mediation grant identity when present."
    )


class RuntimeIdentityEntry(JournalEntry):
    """Persist canonical runtime and public credential identities."""

    binding: RuntimeBinding = Field(description="Admitted native runtime fingerprint.")
    credential: CredentialBinding | None = Field(
        description="Public credential identity, or existing native null."
    )


class CorrectionEntry(JournalEntry):
    """Record correction ordering without mutating terminal run status."""

    turn_id: str = Field(min_length=1, description="Next reserved correction turn.")


class EvidenceEntry(JournalEntry):
    """Native capture metadata; shared terminal-state fields are prohibited."""


class AttemptContext(BaseModel):
    """Host paths and detached current record for provider attempt construction."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    run_id: str = Field(min_length=1, description="Existing host run identity.")
    attempt_id: str = Field(
        min_length=1, description="Current admitted attempt identity."
    )
    workspace: Path = Field(repr=False, description="Admitted execution workspace.")
    evidence: Path = Field(repr=False, description="Private evidence location.")
    record: dict[str, JsonValue] = Field(
        repr=False,
        description="Detached record snapshot; journal owns actual persistence.",
    )


class AttemptRequest(BaseModel):
    """Admitted host execution request; never deserialized directly from graph input."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    context: AttemptContext = Field(description="Owning host attempt context.")
    task: str = Field(repr=False, description="Admitted task text.")
    model: str = Field(description="Explicit selected native model, never substituted.")
    effort: str | None = Field(description="Explicit native effort when selected.")
    resume: bool = Field(
        description="Load the saved native conversation without Fresh fallback."
    )
    native_session: str | None = Field(description="Saved native identity on Resume.")
    deadline: float | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Native attempt deadline only where existing policy supplies one.",
    )

    @model_validator(mode="after")
    def validate_conversation_mode(self):
        """No missing Resume binding or preselected native identity on Fresh."""
        if self.resume != bool(self.native_session):
            raise ValueError("attempt_native_binding_mismatch")
        return self


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


class CredentialAdmission(BaseModel):
    """Public native binding and optional excluded host launch material."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    binding: CredentialBinding = Field(
        description="Admitted public credential metadata."
    )
    material: CredentialMaterial | None = Field(
        default=None,
        exclude=True,
        repr=False,
        description="Explicit host-only native launch material; no universal token requirement.",
    )


class SettlementView(BaseModel):
    """Detached Agent record after freeze or failure, never the live mutable record."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    record: dict[str, JsonValue] = Field(
        repr=False, description="Deep-copied current persisted fields."
    )


class SettlementUpdates(BaseModel):
    """Declared settlement-owned fields; Agent alone owns status/demotion."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    container_ownership: dict[str, JsonValue] | None = Field(
        default=None,
        repr=False,
        description="Existing exact cleanup/grant ownership fields.",
    )
    controller_cleanup: Literal["confirmed", "unverified"] | None = Field(
        default=None, description="Observed controller closure."
    )
    publication_handoff: dict[str, JsonValue] | None = Field(
        default=None, repr=False, description="Existing host publication handoff state."
    )
    evidence: dict[str, JsonValue] = Field(
        default_factory=dict,
        repr=False,
        description="Provider-native evidence, not shared record-state overrides.",
    )

    @model_validator(mode="after")
    def reject_state_override(self):
        if {
            "status",
            "cancel_requested",
            "cancel_confirmed",
            "snapshot_ready",
            "post_run_hash",
            "output_ref",
            "error_category",
        } & self.evidence.keys():
            raise ValueError("reserved_settlement_evidence")
        return self


class SettlementResult(BaseModel):
    """Settlement cleanup truth and declared updates for Agent-owned persistence."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    verified: bool = Field(
        description="Confirmed settlement cleanup, not inferred publication success."
    )
    detail: str | None = Field(default=None, description="Safe scoped cleanup detail.")
    code: str | None = Field(
        default=None, description="Existing stable failure category."
    )
    updates: SettlementUpdates = Field(
        default_factory=SettlementUpdates,
        repr=False,
        description="Declared detached settlement updates applied by Agent.",
    )


class AttemptOutcome(BaseModel):
    """Native attempt result before Agent freeze and any surviving lease settlement."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        hide_input_in_errors=True,
        arbitrary_types_allowed=True,
    )
    status: Literal[
        "completed", "failed", "cancelled", "unknown", "timeout", "interrupted"
    ] = Field(description="Native attempt outcome.")
    native_session: str | None = Field(
        description="Actual native conversation identity, if bound."
    )
    answer: str | None = Field(
        default=None, repr=False, description="Native terminal output."
    )
    turns: tuple[dict[str, JsonValue], ...] = Field(
        description="Detached native turn records."
    )
    error_category: str | None = Field(
        default=None,
        description="Unchanged public category, separate from allowlisted private diagnostics.",
    )
    failure: FailureObservation | None = Field(
        default=None, description="Safe original failure evidence."
    )
    cleanup: RuntimeCleanupReport = Field(
        description="Exact owned resource cleanup facts."
    )
    settlement: BasePostFreezeSettlement | None = Field(
        default=None,
        exclude=True,
        repr=False,
        description="Host-only supervision surviving run, for any outcome status.",
    )


class ScopeCleanupEntry(JournalEntry):
    """Persist exact scope cleanup independently from native terminal result."""

    scope_id: str = Field(description="Single runtime scope identity.")
    report: RuntimeCleanupReport = Field(
        description="Controller and owned resource observations."
    )
