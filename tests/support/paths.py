"""Resolve test assets without coupling them to folder depth or working directory."""

from pathlib import Path


def repository_root():
    """Return the nearest manifest/source checkout or fail with a diagnostic."""
    for directory in Path(__file__).resolve().parents:
        if (directory / "pyproject.toml").is_file() and (
            directory / "src/laomedo"
        ).is_dir():
            return directory
    raise RuntimeError("Test checkout with pyproject.toml and src/laomedo not found")


def error_catalogue_path():
    """Find the single real catalogue in an owning PR or assembled checkout.

    This test-only locator admits both reviewed source layouts and refuses
    duplicate catalogues; it provides no application compatibility path.
    """
    overlay = repository_root() / "frontend/langflow-skill-viewer"
    found = [
        path
        for path in (
            overlay / "errors/node-error-catalog.json",
            overlay / "node-error-catalog.json",
        )
        if path.is_file()
    ]
    if len(found) != 1:
        raise RuntimeError("Expected exactly one shared error catalogue")
    return found[0]
