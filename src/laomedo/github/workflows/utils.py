"""Shared interpretation of native Git paths for GitHub workflow policy."""


def touches_workflows(paths: list[bytes]) -> bool:
    """Return whether the inspected changes include GitHub workflow files."""
    return any(path.startswith(b".github/workflows/") for path in paths if path)
