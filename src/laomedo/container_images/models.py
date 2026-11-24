"""Canonical registered image values and detached build inputs."""

import hashlib
import json
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from laomedo.container_images.errors import ImageBuildError


class ImageRegistration(BaseModel):
    """Trusted portable build identity; no arbitrary request data is accepted."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    image: str = Field(
        pattern=r"^[a-z0-9][a-z0-9./_-]*:[A-Za-z0-9_.-]+$",
        description="Versioned local image tag.",
    )
    context: str = Field(description="Build directory relative to the registry.")
    dockerfile: str = Field(
        default="Dockerfile", description="Dockerfile relative to context."
    )
    files: list[str] = Field(
        min_length=1, description="Exact build inputs; unlisted files are never sent."
    )
    build_args: dict[str, str] = Field(
        default_factory=dict, description="Fixed non-secret build arguments."
    )
    verify_command: list[str] = Field(
        min_length=1, description="Zero-turn command with its own entrypoint."
    )
    verify_output: str = Field(
        min_length=1, description="Required stripped stdout from verification."
    )

    @field_validator("context", "dockerfile")
    @classmethod
    def relative_path(cls, value):
        if (
            not value
            or "\\" in value
            or ":" in value
            or PurePosixPath(value).is_absolute()
            or ".." in PurePosixPath(value).parts
        ):
            raise ValueError("registered_path_must_be_relative")
        return value

    @field_validator("files")
    @classmethod
    def input_paths(cls, values):
        if len(set(values)) != len(values):
            raise ValueError("duplicate_build_input")
        return [cls.relative_path(value) for value in values]

    @model_validator(mode="after")
    def includes_dockerfile(self):
        if self.dockerfile not in self.files:
            raise ValueError("dockerfile_not_registered")
        return self


class ImageRecipe(BaseModel):
    """A registration and its exact bytes, stable throughout lock/build/verify."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    registration: ImageRegistration = Field(description="Validated image registration.")
    inputs: dict[str, bytes] = Field(
        repr=False, exclude=True, description="Detached declared file bytes."
    )
    fingerprint: str = Field(
        description="SHA256 of registration, names and exact bytes."
    )

    @classmethod
    def from_registration(cls, registration, root: Path, *, max_bytes: int):
        root = root.resolve()
        context = root.joinpath(registration.context)
        try:
            context.resolve().relative_to(root.resolve())
            inputs = {}
            total = 0
            digest = hashlib.sha256(
                json.dumps(registration.model_dump(), sort_keys=True).encode()
            )
            for name in sorted(registration.files):
                source = context / name
                source.resolve().relative_to(root.resolve())
                if source.is_symlink() or any(
                    parent.is_symlink()
                    for parent in source.parents
                    if parent.is_relative_to(root)
                ):
                    raise ValueError("symlink_build_input")
                with source.open("rb") as stream:
                    value = stream.read(max_bytes - total + 1)
                total += len(value)
                if total > max_bytes:
                    raise ValueError("build_context_exceeds_bound")
                inputs[name] = value
                encoded = name.encode()
                digest.update(len(encoded).to_bytes(8, "big") + encoded)
                digest.update(len(value).to_bytes(8, "big") + value)
            return cls(
                registration=registration, inputs=inputs, fingerprint=digest.hexdigest()
            )
        except (OSError, ValueError):
            raise ImageBuildError("build_context_invalid") from None

    def write_context(self, directory: Path) -> None:
        """Write only the captured declared inputs into a fresh private directory."""
        for name, value in self.inputs.items():
            destination = directory / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(value)
