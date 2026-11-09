"""Failures values owned by the shared Agent capability."""

from laomedo.agents.agents.base.settings import (
    RUNNER_FAILURE_CODES,
    SDK_FAILURE_CODES,
    SDK_FAILURE_OPERATIONS,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal


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
