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
