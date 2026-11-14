"""OpenCode's native token convention, distinct from normalized Activity usage."""

from pydantic import BaseModel, ConfigDict, Field
from laomedo.agents.activity.models import TokenUsage


class OpenCodeTokenUsage(BaseModel):
    """Five already validated nonnegative native counters."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    non_cached_input: int = Field(
        ge=0, description="Native input excluding cache reads/writes."
    )
    non_reasoning_output: int = Field(
        ge=0, description="Native output excluding reasoning."
    )
    reasoning: int = Field(ge=0, description="Native reasoning output count.")
    cache_read: int = Field(ge=0, description="Native cached input reads.")
    cache_write: int = Field(ge=0, description="Native cached input writes.")
    native_total: int | None = Field(
        default=None,
        ge=0,
        description="Optional observed native total; never filled from a guess.",
    )

    @classmethod
    def from_native(cls, tokens):
        """Reject incomplete native counters instead of inventing zero usage."""
        if not isinstance(tokens, dict) or not isinstance(tokens.get("cache"), dict):
            raise ValueError("Native token counters are incomplete")
        return cls(
            non_cached_input=tokens.get("input"),
            non_reasoning_output=tokens.get("output"),
            reasoning=tokens.get("reasoning"),
            cache_read=tokens["cache"].get("read"),
            cache_write=tokens["cache"].get("write"),
            native_total=tokens.get("total"),
        )

    def plus(self, other: "OpenCodeTokenUsage") -> "OpenCodeTokenUsage":
        """Add disjoint native message counters without changing their convention."""
        return type(self)(
            **{
                name: (
                    value + getattr(other, name)
                    if value is not None and getattr(other, name) is not None
                    else None
                )
                for name, value in self.model_dump().items()
            }
        )

    def to_native_payload(self) -> dict:
        """Preserve the runner's existing native counter field names."""
        return {
            "input": self.non_cached_input,
            "output": self.non_reasoning_output,
            "reasoning": self.reasoning,
            "cache": {"read": self.cache_read, "write": self.cache_write},
            **({"total": self.native_total} if self.native_total is not None else {}),
        }

    def to_activity_usage(self) -> TokenUsage:
        """Preserve the established normalization without double-counting subsets."""
        inputs = self.non_cached_input + self.cache_read + self.cache_write
        outputs = self.non_reasoning_output + self.reasoning
        return TokenUsage(
            input_tokens=inputs,
            cached_input_tokens=self.cache_read,
            cache_write_input_tokens=self.cache_write,
            output_tokens=outputs,
            reasoning_output_tokens=self.reasoning,
            total_tokens=inputs + outputs,
        )
