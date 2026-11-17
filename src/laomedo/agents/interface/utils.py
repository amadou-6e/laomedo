"""Pure public Agent outcome predicates shared by callers and execution."""

import re


def safe_error_code(value, known_codes=()):
    """Project a known or bounded future machine code without arbitrary payloads.

    Known codes are an application-owned allowlist, never caller-supplied data.
    Unknown codes follow the UI diagnostic grammar and exclude sensitive words.
    Return None for values that must be replaced with a safe generic category.
    """
    if not isinstance(value, str):
        return None
    if value in known_codes:
        return value
    if (
        len(value) <= 80
        and re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+){1,15}", value)
        and not re.match(r"(?:sk_|gh[pousr]_|github_pat_)", value, re.IGNORECASE)
        and not re.search(r"secret|password|credential|bearer|token|api_key", value)
    ):
        return value
    return None


def terminal_record(record):
    """Stable terminal states shared by graph clients and asynchronous runner polling."""
    return (
        record.get("status")
        in {"completed", "cancelled", "failed", "timeout", "interrupted"}
        or record.get("status") == "unknown"
        and record.get("attempt_finished") is True
    )
