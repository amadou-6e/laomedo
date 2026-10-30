"""Shared GitHub repository/label admission and canonical resource hashing.

These helpers perform no I/O and grant no authority. URL and owner/name forms
retain their different normalization and error contracts.
"""

from urllib.parse import urlsplit
import hashlib
import json
import re


def validate_repository(repository: str) -> tuple[str, str]:
    """Admit owner/name without case normalization; retain its argument error."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Repository must be owner/name")
    return tuple(repository.split("/"))


def repository_from_url(value):
    """Return the existing lowercase repository identity from an admitted HTTPS URL."""
    if not isinstance(value, str):
        raise ValueError("repository_url_invalid")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.username
        or parsed.password
        or parsed.port
        or parsed.query
        or parsed.fragment
        or not re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?", parsed.path)
    ):
        raise ValueError("repository_url_invalid")
    return parsed.path.strip("/").lower()


def labels_value(value):
    """Admit the existing bounded unique label list and return its sorted copy."""
    if (
        not isinstance(value, list)
        or len(value) > 100
        or any(not isinstance(v, str) or not v or len(v) > 100 for v in value)
        or len(set(value)) != len(value)
    ):
        raise ValueError("labels_invalid")
    return sorted(value)


def issue_digest(value):
    """Hash the unchanged Unicode-preserving canonical JSON resource payload."""
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(
                value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
        ).hexdigest()
    )
