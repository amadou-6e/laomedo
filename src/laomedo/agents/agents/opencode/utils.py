"""Prepare isolated OpenCode commands and normalize native messages."""

from __future__ import annotations

from pathlib import Path
import hashlib
import hmac
import json
import re
from laomedo.agents.agents.opencode.settings import MIN_TOKEN_REMAINING_MS
from laomedo.agents.errors import RunnerError
import secrets
import time
import os
import shutil
import stat
from functools import partial


def remove_controller_directory(root: Path, profile: Path) -> None:
    """Remove only a verified owned staging child, including read-only copies."""
    if (
        not re.fullmatch(r"controller-[0-9a-f]{32}", root.name)
        or root.is_symlink()
        or root.resolve().parent != profile.resolve()
    ):
        raise OSError("opencode_container_cleanup_unverified")
    try:
        observed = root.lstat()
        if getattr(observed, "st_file_attributes", 0) & getattr(
            stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400
        ):
            raise OSError("opencode_container_cleanup_unverified")
        shutil.rmtree(root, onerror=partial(_remove_readonly_controller_file, root))
    except FileNotFoundError:
        if os.path.lexists(root):
            raise


def _remove_readonly_controller_file(root, function, path, error):
    """Retry a Windows read-only owned copy once; preserve other failures."""
    target = Path(path)
    if (
        not isinstance(error[1], PermissionError)
        or target.is_symlink()
        or not target.resolve().is_relative_to(root.resolve())
        or not getattr(target.stat(), "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_READONLY", 1)
        or function not in {os.unlink, os.rmdir}
    ):
        raise error[1]
    target.chmod(target.stat().st_mode | stat.S_IWRITE)
    function(path)


def check_auth_fresh(profile, *, minimum_validity_seconds=None):
    """Check native validity/fingerprint and never weaken the configured minimum TTL."""
    path = Path(profile) / "auth-validity.json"
    try:
        validity = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RunnerError("opencode_auth_validity_required") from exc
    if not isinstance(validity, dict):
        raise RunnerError("opencode_auth_validity_invalid")
    try:
        key = json.loads((Path(profile) / "auth.json").read_text(encoding="utf-8"))[
            "opencode-go"
        ]["key"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RunnerError("opencode_private_auth_required") from exc
    if (
        not isinstance(key, str)
        or validity.get("credential_sha256") != hashlib.sha256(key.encode()).hexdigest()
    ):
        raise RunnerError("opencode_auth_validity_mismatch")
    mode = validity.get("credential_mode")
    if mode == "provider_key" and validity.get("expires_at_ms") is None:
        return
    expiry = validity.get("expires_at_ms")
    if (
        mode != "console_token"
        or not isinstance(expiry, int)
        or isinstance(expiry, bool)
    ):
        raise RunnerError("opencode_auth_validity_invalid")
    required_ms = max(MIN_TOKEN_REMAINING_MS, (minimum_validity_seconds or 0) * 1000)
    if expiry <= int(time.time() * 1000) + required_ms:
        raise RunnerError("opencode_console_token_refresh_required")


def _credential_binding(profile):
    """Return the existing keyed local credential fingerprint; no raw credential is exposed."""
    path = Path(profile) / "credential-binding-key"
    try:
        with path.open("xb") as target:
            target.write(secrets.token_bytes(32))
    except FileExistsError:
        pass
    binding_key = path.read_bytes()
    if len(binding_key) != 32:
        raise RunnerError("opencode_credential_binding_key_invalid")
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
        raise RunnerError("opencode_model_not_connected") from None
    if not models or len({model["id"] for model in models}) != len(models):
        raise RunnerError("opencode_model_not_connected")
    return models
