"""Filesystem admission shared by explicit isolated-runtime configuration."""

import stat


def private_state_path(value):
    """Refuse relative, repository-owned or redirected state; preserve its spelling.

    Missing directories are allowed for later explicit creation. Inspect every
    existing ancestor, including Windows junctions on supported Python 3.10+.
    """
    if not value.is_absolute():
        raise ValueError("graph_runtime_state_invalid")
    for path in (value, *value.parents):
        if (path / ".git").exists():
            raise ValueError("graph_runtime_state_invalid")
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode) or (
            getattr(metadata, "st_file_attributes", 0)
            and metadata.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise ValueError("graph_runtime_state_invalid")
    return value
