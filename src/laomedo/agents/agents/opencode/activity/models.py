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
