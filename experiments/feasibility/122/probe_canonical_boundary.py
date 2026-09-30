"""Credential-free direct-command check of a synthetic canonical store."""

import argparse
import json
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "120"))
from _shared import AppServer, construct_env, inside_git_tree


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", required=True, type=Path)
    parser.add_argument("--profile-dir", required=True, type=Path)
    parser.add_argument("--state-dir", required=True, type=Path)
    args = parser.parse_args()
    codex = args.codex.resolve(strict=True)
    profile = args.profile_dir.resolve(strict=True)
    state = args.state_dir.resolve(strict=True)
    if (state != profile / "issue-122" or inside_git_tree(profile)
            or inside_git_tree(state) or profile.is_symlink()
            or state.is_symlink()):
        raise ValueError("private_roots_invalid")
    run = state / "runs" / str(uuid4())
    draft, canonical = run / "draft", run / "canonical-skill"
    for path in (draft, canonical, state / "home", state / "tmp"):
        path.mkdir(parents=True, exist_ok=True)
    protected = canonical / "SKILL.md"
    protected.write_text("synthetic canonical\n", encoding="utf-8")
    target = canonical / "outside.txt"
    env = construct_env(state / "home", profile / "codex-home", state,
                        codex.parent)
    env["TEMP"] = env["TMP"] = str(state / "tmp")
    report = {"model_calls": 0, "credential_supplied_to_command": False,
              "canonical_under_issue_state": True,
              "temp_is_narrow_sibling": True}
    server = AppServer(codex, draft, env, state,
                       startup_args=["-c", 'windows.sandbox="elevated"'])
    try:
        ok, _ = server.initialize()
        report["initialized"] = ok
        if ok:
            response = server.send("command/exec", {
                "command": [str(Path(env["SystemRoot"]) / "System32" / "cmd.exe"),
                            "/c", f"echo synthetic > {target}"],
                "cwd": str(draft),
                "sandboxPolicy": {"type": "workspaceWrite",
                                  "writableRoots": [str(draft)],
                                  "networkAccess": True},
                "timeoutMs": 10000,
            }, timeout=30)
            report["command_exit_code"] = (
                (response.get("result") or {}).get("exitCode"))
            report["canonical_target_written"] = target.exists()
            report["canonical_skill_unchanged"] = (
                protected.read_text(encoding="utf-8") ==
                "synthetic canonical\n")
            report["canonical_write_boundary_passed"] = (
                not report["canonical_target_written"] and
                report["canonical_skill_unchanged"])
    except Exception as exc:
        report["error_class"] = type(exc).__name__
    finally:
        report["server_close"] = server.close()
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
