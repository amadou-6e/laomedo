"""Typed construction of new registry records; historical readers stay unchanged."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, JsonValue
from laomedo.skills.registry.utils import file_hashes, patch_for, tree_hash


class SkillPolicyReference(BaseModel):
    """Identity of a validated editing policy, without embedding its authority."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    policy_id: str = Field(description="Registry-local policy identity.")
    revision_id: str = Field(description="Admitted policy revision string.")
    hash: str = Field(description="Canonical digest of the entire policy payload.")


class SkillRevisionReference(BaseModel):
    """The byte revision and tree identity used to bind a draft base."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    revision_id: str = Field(
        description="Content-addressed immutable revision identity."
    )
    tree_hash: str = Field(description="Verified canonical file-tree hash.")


class SkillTreeReference(BaseModel):
    """An eligible frozen tree and its path-indexed file hashes."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    tree_hash: str = Field(description="Canonical hash of the proposed byte inventory.")
    file_hashes: dict[str, str] = Field(
        description="Relative path to canonical file hash; dynamic keys remain a map."
    )


class SkillReference(SkillRevisionReference):
    """Public binding of a skill identity to verified immutable bytes."""

    skill_id: str = Field(description="Admitted registry skill identity.")

    def to_reference_payload(self) -> dict:
        """Project only public identity, deliberately excluding full revision metadata."""
        return {
            "skill_id": self.skill_id,
            "revision_id": self.revision_id,
            "tree_hash": self.tree_hash,
        }


class SkillRevision(SkillReference):
    """New immutable registry revision metadata, serialized beside its bundle."""

    file_hashes: dict[str, str] = Field(
        description="Verified path-indexed hashes of copied bundle bytes."
    )
    parent_revision: str | None = Field(
        description="Prior byte revision, explicitly null for an initial import."
    )
    draft_id: str | None = Field(
        description="Originating draft identity, explicitly null for an import."
    )

    def to_record(self) -> dict:
        """Preserve all six existing fields, their order and explicit null values."""
        value = self.model_dump()
        return {
            key: value[key]
            for key in (
                "skill_id",
                "revision_id",
                "tree_hash",
                "file_hashes",
                "parent_revision",
                "draft_id",
            )
        }


class SkillDraft(BaseModel):
    """Identity and policy binding for a newly copied, still-open draft."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    draft_id: str = Field(description="New canonical draft UUID.")
    skill_id: str = Field(description="Registry skill being edited.")
    base_revision: str = Field(description="Verified immutable starting revision.")
    base_tree_hash: str = Field(description="Starting file-tree identity.")
    policy_ref: SkillPolicyReference = Field(
        description="Validated policy identity for this draft."
    )
    status: Literal["open"] = Field(
        default="open",
        description="New drafts are open; service-owned transitions remain on disk.",
    )

    def to_record(self) -> dict:
        """Return the existing draft file shape, including the initial status."""
        return self.model_dump()


class SkillValidationResult(BaseModel):
    """One structural check and its stable machine-code failures."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    validator: Literal["structural-v1"] = Field(
        default="structural-v1", description="Existing structural validator identity."
    )
    passed: bool = Field(description="Whether this check observed no errors.")
    errors: list[str] = Field(description="Sorted unique stable error codes.")


class FrozenSkillDraft(BaseModel):
    """Review artifact; eligibility is evidence and never performs promotion."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    draft_id: str = Field(description="Draft whose observed bytes were reviewed.")
    base_ref: SkillRevisionReference = Field(
        description="Verified starting revision and tree."
    )
    policy_ref: SkillPolicyReference = Field(
        description="Policy validated before review."
    )
    editor_kind: Literal["human", "operator", "agent"] = Field(
        description="Admitted host-supplied editing provenance kind."
    )
    edit_run_id: JsonValue = Field(
        description="Existing JSON provenance value; admission requires a nonempty string for agent edits."
    )
    trace_ref: JsonValue = Field(
        description="Legacy caller-supplied JSON provenance reference; preserved without stronger admission."
    )
    observed_tree_hash: str | None = Field(
        description="Observed inventory hash, null when inventory failed."
    )
    proposed_tree_hash: str | None = Field(
        description="Observed hash only when eligible; otherwise null."
    )
    proposed_ref: SkillTreeReference | None = Field(
        description="Eligible frozen tree metadata, otherwise null."
    )
    changed_paths: list[str] = Field(
        description="Sorted paths whose bytes differ from the base."
    )
    patch: str | None = Field(
        description="Existing exact unified patch, null if inventory failed."
    )
    validation_errors: list[str] = Field(
        description="Sorted unique structural failure codes."
    )
    validation_results: list[SkillValidationResult] = Field(
        description="Recorded structural check results."
    )
    evaluation_results: list[JsonValue] = Field(
        default_factory=list,
        description="Existing empty evaluation extension; no evaluation is inferred.",
    )
    promotion_eligible: bool = Field(
        description="Whether observed bytes passed all structural checks."
    )
    promotion_performed: Literal[False] = Field(
        default=False, description="Freezing never promotes canonical latest."
    )

    @classmethod
    def from_review(
        cls,
        record: dict,
        base: dict[str, bytes],
        proposed: dict[str, bytes] | None,
        errors: list[str],
        *,
        draft_id: str,
        editor_kind: str,
        edit_run_id: JsonValue,
        trace_ref: JsonValue,
    ) -> "FrozenSkillDraft":
        """Derive one coherent result after existing store admission and byte checks.

        The legacy record reader remains authoritative; this constructs the new
        review artifact rather than revalidating the historical draft schema.
        """
        eligible = proposed is not None and not errors
        observed = tree_hash(proposed) if proposed is not None else None
        failures = sorted(set(errors))
        return cls(
            draft_id=draft_id,
            base_ref=SkillRevisionReference(
                revision_id=record["base_revision"], tree_hash=record["base_tree_hash"]
            ),
            policy_ref=SkillPolicyReference(**record["policy_ref"]),
            editor_kind=editor_kind,
            edit_run_id=edit_run_id,
            trace_ref=trace_ref,
            observed_tree_hash=observed,
            proposed_tree_hash=observed if eligible else None,
            proposed_ref=(
                SkillTreeReference(
                    tree_hash=observed, file_hashes=file_hashes(proposed)
                )
                if eligible
                else None
            ),
            changed_paths=(
                sorted(
                    path
                    for path in base.keys() | proposed.keys()
                    if base.get(path) != proposed.get(path)
                )
                if proposed is not None
                else []
            ),
            patch=patch_for(base, proposed) if proposed is not None else None,
            validation_errors=failures,
            validation_results=[
                SkillValidationResult(passed=not errors, errors=failures)
            ],
            promotion_eligible=eligible,
        )

    def to_record(self) -> dict:
        """Preserve explicit nulls, empty results and the sixteen-field review shape."""
        value = self.model_dump()
        # The old freeze path read this reference from sorted-key disk JSON.
        value["policy_ref"] = dict(sorted(value["policy_ref"].items()))
        return value
