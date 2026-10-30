"""Canonical admitted source values; historical index readers remain unchanged."""

from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class AdmittedSkillSource(BaseModel):
    """The existing source kind and normalized location after feature admission."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    kind: Literal["local", "repository", "registry"] = Field(
        description="Existing admitted source category."
    )
    location: str = Field(description="Existing normalized URL or absolute local path.")


class SkillSourceChoice(BaseModel):
    """Fresh discovery choice; historical cached choices keep their existing readers."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    choice: str = Field(
        description="Existing selector label, including its original delimiter."
    )
    name: str = Field(description="Existing admitted skill name.")
    path: str = Field(
        description="Source-relative skill folder, including the root marker."
    )

    @classmethod
    def for_folder(cls, name: str, path: str) -> "SkillSourceChoice":
        return cls(choice=name + " | " + path, name=name, path=path)

    @classmethod
    def for_registry(cls, name: str) -> "SkillSourceChoice":
        return cls(choice=name, name=name, path="skills/" + name)

    def to_record(self) -> dict:
        return {"choice": self.choice, "name": self.name, "path": self.path}


class SkillRepositoryRef(BaseModel):
    """One captured source ref label and its resolved Git commit."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    label: str = Field(
        description="Existing ref label after removing the refs/ prefix."
    )
    commit: str = Field(
        description="Resolved commit string; no new normalization or admission."
    )


class SkillRepositoryState(BaseModel):
    """An owned source-cache directory and its bounded captured reference list."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    directory: Path = Field(
        repr=False, exclude=True, description="Owned bare-repository cache directory."
    )
    refs: list[SkillRepositoryRef] = Field(
        description="Captured source refs, preserving Git enumeration order."
    )


class PendingSkillImport(BaseModel):
    """Exact collected bytes and origin awaiting the existing option-limit checks."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    files: dict[str, bytes] = Field(
        repr=False,
        exclude=True,
        description="Exact admitted candidate bytes, without coercion or newline conversion.",
    )
    origin: str = Field(
        description="Existing source provenance string, kept outside hashed bundles."
    )
