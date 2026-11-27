"""Pinned host component identities for saved-account graph admission."""

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


class ResourceBinding(BaseModel):
    """Safe resource identity and version; never an endpoint, config or credential."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["skill", "mcp"] = Field(
        description="Concern owning the resource reference."
    )
    id: str = Field(
        min_length=1, max_length=200, description="Owner-validated opaque identity."
    )
    version: str = Field(
        min_length=1,
        max_length=200,
        description="Immutable Skill revision or MCP configuration epoch.",
    )


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
