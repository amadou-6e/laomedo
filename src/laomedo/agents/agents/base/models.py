"""Public provider binding carried as one strict internal lifecycle value."""

from pydantic import BaseModel, ConfigDict, Field
from pydantic import JsonValue
from typing import ClassVar, Literal
import hashlib
from laomedo.agents.artifacts.models import ArtifactReference
from laomedo.agents.interface.models import PrecheckEvidence
from laomedo.agents.orchestration.models import HandoffProvenance


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
