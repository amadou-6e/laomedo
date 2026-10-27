"""Installed paths independent of domain module nesting depth."""
from pathlib import Path


def package_root() -> Path:
    """Return the unpacked installed package directory.

    Returns
    -------
    Path
        Canonical package directory for editable and wheel installations.
    """
    return Path(__file__).resolve().parent


def import_root() -> Path:
    """Return the directory containing the importable package.

    Returns
    -------
    Path
        Source import directory or installed site-packages directory.
    """
    return package_root().parent
