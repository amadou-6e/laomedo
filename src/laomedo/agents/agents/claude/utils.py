"""Normalize Claude commands, native results and model capabilities."""

from __future__ import annotations

import json
import laomedo.agents.agents.claude.catalog as _claude_catalog
import laomedo.agents.agents.claude.settings as _claude_settings
import laomedo.agents.errors as _runtime_errors
import re


def activity_usage(result):
    """Normalize cumulative session modelUsage; never add resumed totals together.

    Claude inputTokens excludes cache reads/writes; the shared activity schema
    includes them in inputTokens. Missing categories remain unknown.
    """
    models = result.get("modelUsage")
    if not isinstance(models, dict) or not models:
        return None
    keys = (
        "inputTokens",
        "cacheReadInputTokens",
        "cacheCreationInputTokens",
        "outputTokens",
    )
    if any(
        not isinstance(value, dict)
        or any(type(value.get(key)) is not int or value[key] < 0 for key in keys)
        for value in models.values()
    ):
        return None
    totals = {key: sum(value[key] for value in models.values()) for key in keys}
    inputs = (
        totals["inputTokens"]
        + totals["cacheReadInputTokens"]
        + totals["cacheCreationInputTokens"]
    )
    normalized = {
        "inputTokens": inputs,
        "cachedInputTokens": totals["cacheReadInputTokens"],
        "cacheWriteInputTokens": totals["cacheCreationInputTokens"],
        "outputTokens": totals["outputTokens"],
        "totalTokens": inputs + totals["outputTokens"],
    }
    if all(
        type(value.get("thinkingTokens")) is int
        and 0 <= value["thinkingTokens"] <= value["outputTokens"]
        for value in models.values()
    ):
        normalized["reasoningOutputTokens"] = sum(
            value["thinkingTokens"] for value in models.values()
        )
    return normalized


def configuration_hash(model, effort, skills):
    """Fingerprint the same canonical ACP options that execution will apply."""
    from laomedo.agents.agents.claude.models import ClaudePolicy

    return ClaudePolicy(
        model=model, effort=effort, skill_ids=tuple(item["skill_id"] for item in skills)
    ).fingerprint()


def terminal_result(text, thread):
    """Require Claude's terminal receipt; never repair its proposed answer."""
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        raise _runtime_errors.RunnerError("claude_terminal_receipt_invalid") from None
    if (
        not isinstance(value, dict)
        or value.get("type") != "result"
        or value.get("session_id") != thread
    ):
        raise _runtime_errors.RunnerError("claude_session_identity_mismatch")
    if value.get("is_error") or value.get("subtype") != "success":
        raise _runtime_errors.RunnerError("claude_native_turn_failed")
    if (
        type(value.get("num_turns", 1)) is not int
        or value.get("num_turns", 1) < 1
        or (value.get("subagent_stats") or {}).get("spawned", 0)
    ):
        raise _runtime_errors.RunnerError("claude_native_turn_limit_mismatch")
    if not isinstance(value.get("result"), str) or not value["result"].strip():
        raise _runtime_errors.RunnerError("completed_without_agent_message")
    return value


def normalize_models(items):
    """Keep native picker IDs/labels and each model's advertised effort levels."""
    if not isinstance(items, list) or not items or len(items) > 256:
        raise ValueError("invalid_native_models")
    models, seen = [], set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("invalid_native_model")
        model, name, resolved = (
            item.get("value"),
            item.get("displayName"),
            item.get("resolvedModel"),
        )
        if (
            not isinstance(model, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.\[\]-]{0,159}", model)
            or model in seen
            or not isinstance(name, str)
            or not name.strip()
            or len(name) > 200
            or not isinstance(resolved, str)
            or not re.fullmatch(r"claude-[A-Za-z0-9_.-]{1,160}", resolved)
        ):
            raise ValueError("invalid_native_model")
        seen.add(model)
        levels = item.get("supportedEffortLevels", [])
        if item.get("supportsEffort") is True:
            if (
                not isinstance(levels, list)
                or not levels
                or any(
                    not isinstance(level, str)
                    or level not in _claude_catalog.EFFORTS
                    or level == "default"
                    for level in levels
                )
                or len(set(levels)) != len(levels)
            ):
                raise ValueError("invalid_native_efforts")
        elif item.get("supportsEffort") not in (None, False) or levels:
            raise ValueError("invalid_native_efforts")
        else:
            levels = [
                "default"
            ]  # Explicitly omit --effort for models without this control.
        models.append(
            {"id": model, "name": name, "resolved_model": resolved, "efforts": levels}
        )
    return models
