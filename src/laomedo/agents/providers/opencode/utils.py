"""Prepare isolated OpenCode commands and normalize native messages."""

from __future__ import annotations

from pathlib import Path
import hashlib
import hmac
import json
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


def normalize_message(message, skills):
    """Require terminal assistant metadata; normalize observed native tool results."""
    info = message.get("info") or {}
    if info.get("role") != "assistant" or not info.get("time", {}).get("completed"):
        raise _runtime_errors.RunnerError("opencode_response_not_terminal")
    if info.get("error"):
        raise _runtime_errors.RunnerError("opencode_provider_error")
    answer, tools = [], []
    for part in message.get("parts", []):
        if part.get("type") == "text":
            answer.append(part.get("text", ""))
        elif part.get("type") == "tool":
            state = part.get("state") or {}
            tools.append(
                {
                    "call_id": part.get("callID"),
                    "tool": part.get("tool"),
                    "status": state.get("status"),
                    "input": state.get("input"),
                    "output": state.get("output"),
                    "error": state.get("error"),
                }
            )
            if state.get("status") in {"pending", "running"}:
                raise _runtime_errors.RunnerError("opencode_outstanding_tool")
            if part.get("tool") == "skill" and state.get("status") == "completed":
                tool_input = state.get("input")
                if not isinstance(tool_input, dict):
                    tool_input = {}
                for skill in skills:
                    if tool_input.get("name") == skill["skill_id"]:
                        skill["use_evidence"] = "native_skill_tool_completed"
    if not any(answer):
        raise _runtime_errors.RunnerError("completed_without_agent_message")
    return {
        "answer": "\n".join(answer),
        "native_turn_id": info.get("id"),
        "usage": info.get("tokens") if isinstance(info.get("tokens"), dict) else None,
        "tools": tools,
    }


def turn_parts(message, steps):
    """Keep the latest state of each native tool call, including final-message parts."""
    info = message.get("info") or {}
    parts = []
    if isinstance(steps, list) and info.get("parentID"):
        for step in steps:
            step_info = step.get("info") or {}
            if (
                step_info.get("role") == "assistant"
                and step_info.get("parentID") == info["parentID"]
            ):
                parts.extend(
                    part for part in step.get("parts", []) if part.get("type") == "tool"
                )
    parts.extend(message.get("parts", []))
    merged, positions = [], {}
    for part in parts:
        call_id = part.get("callID") if part.get("type") == "tool" else None
        if call_id and call_id in positions:
            merged[positions[call_id]] = part
        else:
            if call_id:
                positions[call_id] = len(merged)
            merged.append(part)
    return merged
