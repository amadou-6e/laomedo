"""Shared harness for the Claude Agent SDK probes (issue 121).

Coded against the verified surface of claude-agent-sdk 0.2.161:
- ClaudeAgentOptions: cwd, env, setting_sources, skills, model, effort,
  permission_mode, allowed_tools, max_turns, max_budget_usd, resume,
  fork_session, include_partial_messages, stderr.
- Messages: SystemMessage(subtype, data), AssistantMessage(content blocks,
  model, usage), UserMessage, ResultMessage(subtype, session_id, usage,
  model_usage, terminal_reason, errors), StreamEvent.
- Blocks: TextBlock, ThinkingBlock, ToolUseBlock(id, name, input),
  ToolResultBlock(tool_use_id, content, is_error), ServerToolUseBlock,
  ServerToolResultBlock.
- Errors: CLINotFoundError, CLIConnectionError, ProcessError, ResultError,
  CLIJSONDecodeError.

No credential value is ever printed. Personal roots are compared by hash.
"""

import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys


PERSONAL_ROOT_NAMES = [
    "user_skills",
    "user_commands",
    "user_settings.json",
    "user_claude.json",
    "user_projects",
    "user_plugins",
]


def personal_roots():
    home = Path.home()
    return [
        home / ".claude" / "skills",
        home / ".claude" / "commands",
        home / ".claude" / "settings.json",
        home / ".claude.json",
        home / ".claude" / "projects",
        home / ".claude" / "plugins",
    ]


def fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    if not root.exists():
        return "absent"
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        if path.is_file():
            with path.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    digest.update(chunk)
    return digest.hexdigest()


def hash_path(path: Path) -> str:
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    return fingerprint(path)


def hash_personal_roots():
    return [hash_path(root) for root in personal_roots()]


def compare_personal_roots(before, after):
    return dict(zip(PERSONAL_ROOT_NAMES, (a == b for a, b in zip(before, after))))


def inside_git_tree(path: Path) -> bool:
    for candidate in [path.resolve(), *path.resolve().parents]:
        if (candidate / ".git").exists():
            return True
    return False


def ensure_clean(path: Path) -> int:
    """(Re)create a run directory. Returns the count of entries that could not
    be removed (for example a file locked by Windows)."""
    leftover = 0
    if path.exists():
        for child in sorted(path.rglob("*"), reverse=True):
            try:
                if child.is_dir() and not child.is_symlink():
                    child.rmdir()
                else:
                    child.unlink()
            except OSError:
                leftover += 1
        leftover += len(list(path.rglob("*")))
    path.mkdir(parents=True, exist_ok=True)
    return leftover


def resettable_dir(root: Path) -> tuple:
    """A run directory safe to reset, guarded against deleting anything
    outside the experiment tree. Returns (resolved_path, leftover_count)."""
    experiment = Path(__file__).resolve().parent
    resolved = root.resolve()
    if not resolved.is_relative_to(experiment):
        raise ValueError("refusing to reset a directory outside the experiment tree")
    leftovers = ensure_clean(resolved)
    return resolved, leftovers


def write_skill(root: Path, name: str, description: str, content: str = None):
    """Create <root>/<name>/SKILL.md with a description so the skill is
    user-invocable and appears in the init skills array."""
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    if content is None:
        content = "This fixture is synthetic probe content.\n"
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{content}",
        encoding="utf-8",
    )
    return skill_dir


def sdk_version() -> str:
    try:
        import importlib.metadata as metadata
        return metadata.version("claude-agent-sdk")
    except Exception:
        return "not-installed"


def runner_versions() -> dict:
    versions = {
        "sdk": sdk_version(),
        "python": platform.python_version(),
        "platform": f"{platform.system()} {platform.machine()}",
        "node": None,
    }
    try:
        result = subprocess.run(["node", "--version"], capture_output=True,
                                text=True, timeout=20, encoding="utf-8")
        versions["node"] = result.stdout.strip() or result.stderr.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return versions


def resolve_cli():
    """Resolve the Claude Code CLI the way the SDK does. Returns
    (path_or_None, error_message_or_None). Never spawns a model call."""
    from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport
    from claude_agent_sdk import ClaudeAgentOptions
    transport = SubprocessCLITransport(prompt="x", options=ClaudeAgentOptions())
    try:
        return transport._find_cli(), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def cli_version(cli_path: str) -> str:
    try:
        result = subprocess.run([cli_path, "--version"], capture_output=True,
                                text=True, timeout=30, encoding="utf-8",
                                errors="replace")
        return (result.stdout + result.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return f"unavailable: {type(exc).__name__}"


def tcp_reachable(host: str, port: int = 443, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def credential_gate(state: Path, config_dir: Path) -> dict:
    """Decide whether a model call is permitted.

    Accepts only a dedicated ANTHROPIC_API_KEY from the runner environment.
    Rejects a state dir inside a git tree, a missing key, a personal OAuth
    token present in the private config dir (a copied login), and an
    unreachable api.anthropic.com. Never reads or prints the key value.
    """
    verdict = {"permitted": False, "credential_mode": None}
    if inside_git_tree(state):
        verdict["reason"] = "state_dir_inside_git_tree"
        return verdict
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key.strip():
        verdict["reason"] = "missing_anthropic_api_key"
        return verdict
    for token_name in (".credentials.json", "credentials.json"):
        if (config_dir / token_name).is_file():
            verdict["reason"] = "personal_oauth_token_in_config_dir"
            return verdict
    verdict["credential_mode"] = "anthropic_api_key"
    if not tcp_reachable("api.anthropic.com"):
        verdict["reason"] = "api_anthropic_unreachable"
        return verdict
    verdict["permitted"] = True
    return verdict


def options_env(private_home: Path, config_dir: Path, api_key: str = None) -> dict:
    """Environment passed to the CLI subprocess via options.env. The SDK merges
    this on top of the inherited process environment, so every personal-profile
    variable is overridden explicitly."""
    env = {
        "HOME": str(private_home),
        "USERPROFILE": str(private_home),
        "CLAUDE_CONFIG_DIR": str(config_dir),
        "DISABLE_TELEMETRY": "1",
        "DISABLE_ERROR_REPORTING": "1",
        "DISABLE_AUTOUPDATER": "1",
    }
    if api_key is not None:
        env["ANTHROPIC_API_KEY"] = api_key
    return env


def count_attempted_turn(summary: dict) -> None:
    """Count a turn immediately before submitting it. The count is an upper
    bound on billable model calls: a submitted turn may still be rejected
    before generation, but every billable call must have been submitted."""
    summary["model_calls"] = summary.get("model_calls", 0) + 1


def redact_message(message) -> dict:
    """Sanitized view of one SDK message. Never includes file contents, prompt
    text, or result text; string lengths and key names only."""
    kind = type(message).__name__
    view = {"kind": kind}
    if kind == "SystemMessage":
        data = message.data or {}
        view["subtype"] = message.subtype
        if message.subtype == "init":
            skills = data.get("skills") or []
            view["data_keys"] = sorted(data.keys())
            view["session_id"] = data.get("session_id")
            view["model"] = data.get("model")
            view["skill_names"] = sorted(str(s) for s in skills)
            view["slash_command_count"] = len(data.get("slash_commands") or [])
            view["version"] = data.get("version")
    elif kind == "AssistantMessage":
        view["model"] = message.model
        view["session_id"] = message.session_id
        view["stop_reason"] = message.stop_reason
        blocks = []
        for block in (message.content or []):
            bkind = type(block).__name__
            entry = {"kind": bkind}
            if bkind == "ToolUseBlock":
                entry["id"] = block.id
                entry["name"] = block.name
                entry["input_keys"] = sorted((block.input or {}).keys())
            elif bkind == "TextBlock":
                entry["text_length"] = len(block.text or "")
            elif bkind == "ToolResultBlock":
                entry["tool_use_id"] = block.tool_use_id
                entry["is_error"] = block.is_error
            blocks.append(entry)
        view["blocks"] = blocks
        view["usage"] = message.usage
    elif kind == "UserMessage":
        blocks = []
        content = message.content
        if isinstance(content, list):
            for block in content:
                bkind = type(block).__name__
                entry = {"kind": bkind}
                if bkind == "ToolResultBlock":
                    entry["tool_use_id"] = block.tool_use_id
                    entry["is_error"] = block.is_error
                    text = block.content if isinstance(block.content, str) else ""
                    entry["content_length"] = len(text or "")
                blocks.append(entry)
        view["blocks"] = blocks
    elif kind == "ResultMessage":
        view.update({
            "subtype": message.subtype,
            "is_error": message.is_error,
            "num_turns": message.num_turns,
            "session_id": message.session_id,
            "total_cost_usd": message.total_cost_usd,
            "api_error_status": message.api_error_status,
            "terminal_reason": message.terminal_reason,
            "errors": message.errors,
            "usage": message.usage,
            "model_usage_models": sorted((message.model_usage or {}).keys())
                                  if message.model_usage else [],
        })
    elif kind == "StreamEvent":
        event = message.event or {}
        view["event_type"] = event.get("type")
        view["session_id"] = message.session_id
    return view


def collect_events(messages) -> dict:
    """Summarize a message list: tool calls, matching results, terminal state."""
    tool_calls = {}
    tool_results = []
    init_view = None
    result_view = None
    redacted = []
    for message in messages:
        view = redact_message(message)
        redacted.append(view)
        if view["kind"] == "AssistantMessage":
            for block in view["blocks"]:
                if block["kind"] == "ToolUseBlock":
                    tool_calls[block["id"]] = block["name"]
        elif view["kind"] == "UserMessage":
            for block in view["blocks"]:
                if block["kind"] == "ToolResultBlock":
                    tool_results.append(block["tool_use_id"])
        elif view["kind"] == "SystemMessage" and view.get("subtype") == "init":
            init_view = view
        elif view["kind"] == "ResultMessage":
            result_view = view
    return {
        "message_count": len(redacted),
        "events": redacted,
        "init": init_view,
        "result": result_view,
        "tool_call_ids": sorted(tool_calls),
        "tool_call_names": sorted(set(tool_calls.values())),
        "tool_result_ids": sorted(tool_results),
        "tool_results_matched": sorted(set(tool_calls) & set(tool_results)),
        "tool_call_and_result_observed": bool(tool_calls) and bool(set(tool_calls) & set(tool_results)),
    }
