"""Prepare isolated OpenCode commands and normalize native messages."""

from __future__ import annotations

from pathlib import Path
import hashlib
import hmac
import json
import re
import laomedo.agents.providers.opencode.settings as _opencode_settings
import laomedo.agents.runtime.errors as _runtime_errors
import secrets
import time


def check_auth_fresh(profile):
    path = Path(profile) / "auth-validity.json"
    try:
        validity = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise _runtime_errors.RunnerError("opencode_auth_validity_required") from exc
    if not isinstance(validity, dict):
        raise _runtime_errors.RunnerError("opencode_auth_validity_invalid")
    try:
        key = json.loads((Path(profile) / "auth.json").read_text(encoding="utf-8"))[
            "opencode-go"
        ]["key"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise _runtime_errors.RunnerError("opencode_private_auth_required") from exc
    if (
        not isinstance(key, str)
        or validity.get("credential_sha256") != hashlib.sha256(key.encode()).hexdigest()
    ):
        raise _runtime_errors.RunnerError("opencode_auth_validity_mismatch")
    mode = validity.get("credential_mode")
    if mode == "provider_key" and validity.get("expires_at_ms") is None:
        return
    expiry = validity.get("expires_at_ms")
    if (
        mode != "console_token"
        or not isinstance(expiry, int)
        or isinstance(expiry, bool)
    ):
        raise _runtime_errors.RunnerError("opencode_auth_validity_invalid")
    if expiry <= int(time.time() * 1000) + _opencode_settings.MIN_TOKEN_REMAINING_MS:
        raise _runtime_errors.RunnerError("opencode_console_token_refresh_required")


def _credential_binding(profile):
    path = Path(profile) / "credential-binding-key"
    try:
        with path.open("xb") as target:
            target.write(secrets.token_bytes(32))
    except FileExistsError:
        pass
    binding_key = path.read_bytes()
    if len(binding_key) != 32:
        raise _runtime_errors.RunnerError("opencode_credential_binding_key_invalid")
    fingerprint = json.loads((Path(profile) / "auth-validity.json").read_text())[
        "credential_sha256"
    ]
    return hmac.new(binding_key, fingerprint.encode(), hashlib.sha256).hexdigest()


def model_metadata(text):
    """Parse native models --verbose records; reject incomplete or conflicting IDs."""
    decoder = json.JSONDecoder()
    models = []
    remaining = text.strip()
    try:
        while remaining:
            identity, separator, remaining = remaining.partition("\n")
            if not separator or not re.fullmatch(
                r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.:-]+", identity
            ):
                raise ValueError()
            remaining = remaining.lstrip()
            metadata, size = decoder.raw_decode(remaining)
            if metadata.get("providerID") + "/" + metadata.get("id") != identity:
                raise ValueError()
            models.append(
                {"id": identity, "efforts": ["default"], "metadata": metadata}
            )
            remaining = remaining[size:].strip()
    except (ValueError, TypeError, AttributeError):
        raise _runtime_errors.RunnerError("opencode_model_not_connected") from None
    if not models or len({model["id"] for model in models}) != len(models):
        raise _runtime_errors.RunnerError("opencode_model_not_connected")
    return models
