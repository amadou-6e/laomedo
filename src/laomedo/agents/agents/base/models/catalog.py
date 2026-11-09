"""Catalog values owned by the shared Agent capability."""

from pydantic import BaseModel, ConfigDict, Field


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
