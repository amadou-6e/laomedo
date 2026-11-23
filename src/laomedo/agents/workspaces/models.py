"""Canonical private working-state inputs and preparation results."""

from pathlib import Path, PurePosixPath
from laomedo.agents.workspaces.utils import is_link
from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorkspaceFiles(BaseModel):
    """Bounded initial text files copied into a fresh run, never host path authority."""

    model_config = ConfigDict(strict=True, extra="forbid", hide_input_in_errors=True)
    files: dict[str, str] = Field(default_factory=dict, max_length=256, repr=False)

    @model_validator(mode="after")
    def validate_files(self):
        """Keep user files beneath project/ and below the local HTTP body budget."""
        if len(self.model_dump_json().encode()) > 262144:
            raise ValueError("workspace_files_too_large")
        for path in self.files:
            parts = path.split("/")
            if (
                len(path) > 500
                or len(parts) < 2
                or parts[0] != "project"
                or PurePosixPath(path).is_absolute()
                or any(
                    part.lower() in {"", ".", "..", ".git", ".agents"}
                    or ":" in part
                    or "\\" in part
                    or any(ord(c) < 32 for c in part)
                    or part.endswith((".", " "))
                    for part in parts
                )
            ):
                raise ValueError("workspace_file_path_invalid")
        return self

    def materialize(self, workspace: Path):
        """Create files once; refuse collisions and links in the prepared workspace."""
        for relative, content in self.files.items():
            path = workspace.joinpath(*relative.split("/"))
            if any(is_link(p) for p in (path, *path.parents)):
                raise ValueError("workspace_file_path_invalid")
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8", newline="") as output:
                output.write(content)

    @classmethod
    def from_workspace(cls, workspace: Path):
        """Read regular project text only, refusing links, binary and oversized files."""
        root = workspace / "project"
        if is_link(root):
            raise ValueError("workspace_file_path_invalid")
        if not root.exists():
            return cls()
        pending = [root]
        files = {}
        scanned = 0
        while pending:
            directory = pending.pop()
            if is_link(directory):
                raise ValueError("workspace_file_path_invalid")
            for path in directory.iterdir():
                scanned += 1
                if scanned > 512 or is_link(path):
                    raise ValueError("workspace_files_invalid")
                if path.is_dir():
                    pending.append(path)
                elif path.is_file():
                    if path.stat().st_size > 262144:
                        raise ValueError("workspace_files_too_large")
                    files[path.relative_to(workspace).as_posix()] = path.read_text(
                        encoding="utf-8"
                    )
                    cls(files=files)
        return cls(files=files)


class WorkspacePaths(BaseModel):
    """Group the admitted source and owned run directory without filesystem effects."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    source: Path = Field(
        repr=False,
        exclude=True,
        description="Trusted host source; preparation checks its actual state.",
    )
    directory: Path = Field(
        repr=False,
        exclude=True,
        description="New run-owned working directory; never overwrite an existing directory.",
    )


class WorkspaceSnapshot(BaseModel):
    """Observed preparation result, distinct from authority to execute or publish."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    source_hash: str = Field(
        description="Existing canonical file-tree hash, preserving its serialized format."
    )
    baseline: str | None = Field(
        default=None,
        description="Observed source commit for Git mode; absent for a copied directory.",
    )
