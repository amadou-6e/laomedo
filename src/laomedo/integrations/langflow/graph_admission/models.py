"""Pinned host component identities for saved-account graph admission."""

from pydantic import BaseModel, ConfigDict, Field


class GitHubCatalogEntry(BaseModel):
    """One immutable canonical host code identity, never a browser assertion."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    component_type: str = Field(
        min_length=1, description="Exact canonical key from the trusted host catalog."
    )
    classification: str = Field(
        min_length=1,
        description="Host-template execution class explicitly classified by the maintainer.",
    )
    code_digest: str = Field(
        pattern=r"^[0-9a-f]{64}$",
        description="Full SHA-256 of the host's executable component source.",
    )


class GitHubCatalogSnapshot(BaseModel):
    """Frozen classified code identities pinned across one saved-account run."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    entries: tuple[GitHubCatalogEntry, ...] = Field(
        min_length=1,
        description="Host-captured canonical sources approved for this runtime.",
    )
