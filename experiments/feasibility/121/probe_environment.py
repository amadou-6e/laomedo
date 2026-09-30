"""Probe the Claude Agent SDK environment without a credential or model call.

This probe never sends an authenticated model call. It records:
- SDK, Python, Node versions, and the resolved Claude Code CLI version.
- Whether the installed wheel bundles or finds a CLI at all.
- That session start fails explicitly without a credential (a deliberately
  invalid API key cannot bill, so this is spend-safe).
- That personal roots are unchanged.
"""

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", action="store_true",
                        help="reset the scratch directory before running")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _shared import (compare_personal_roots, ensure_clean, hash_personal_roots,
                          options_env, personal_roots, resettable_dir,
                          resolve_cli, cli_version, runner_versions)

    summary = dict(runner_versions())
    state, leftovers = resettable_dir(
        Path(__file__).resolve().parent / "_scratch_121_env")
    summary["scratch_leftovers"] = leftovers
    private_home = state / "home"
    config_dir = state / "claude-config"
    private_home.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    before = hash_personal_roots()

    cli_path, cli_error = resolve_cli()
    summary["cli_resolved"] = bool(cli_path)
    summary["cli_error"] = cli_error
    if cli_path:
        summary["cli_version"] = cli_version(cli_path)

    # Auth-failure evidence: a deliberately invalid key fails explicitly and
    # cannot produce a billable model call. This exercises session start in the
    # private profile without touching any real account.
    try:
        from claude_agent_sdk import ClaudeAgentOptions, query
        from claude_agent_sdk._errors import CLINotFoundError, CLIConnectionError, ProcessError

        async def attempt():
            options = ClaudeAgentOptions(
                cwd=str(state),
                env=options_env(private_home, config_dir, state,
                                api_key="invalid-laomedo-121-no-spend"),
                setting_sources=[],
                max_turns=1,
                permission_mode="default",
            )
            outcome = {"auth_failure_observed": False}
            try:
                async for message in query(prompt="Reply with ok.", options=options):
                    pass
            except (CLINotFoundError, CLIConnectionError) as exc:
                outcome["outcome"] = "cli_unavailable"
                outcome["error"] = f"{type(exc).__name__}"
            except ProcessError as exc:
                outcome["outcome"] = "process_error"
                outcome["exit_code"] = getattr(exc, "exit_code", None)
                text = (getattr(exc, "stderr", "") or "")
                lowered = text.lower()
                outcome["auth_signal"] = any(word in lowered for word in
                                             ("api key", "auth", "login", "401", "credit"))
                outcome["error"] = f"{type(exc).__name__}"
            except Exception as exc:
                outcome["outcome"] = "other_error"
                outcome["error"] = type(exc).__name__
            else:
                outcome["outcome"] = "unexpected_success"
            return outcome

        summary["no_credential_session_start"] = asyncio.run(attempt())
    except ImportError as exc:
        summary["no_credential_session_start"] = {
            "outcome": "sdk_import_failed",
            "error": type(exc).__name__,
        }

    summary["config_dir_created"] = config_dir.is_dir()
    summary["personal_roots_unchanged"] = compare_personal_roots(
        before, hash_personal_roots())
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
