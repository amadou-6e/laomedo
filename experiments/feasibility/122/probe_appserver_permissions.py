"""Credential-free Codex app-server write-permission compatibility check.

No turn/start is sent, and no personal or private credential is loaded.
"""

import argparse
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "120"))
from _shared import AppServer, codex_version, construct_env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", required=True, type=Path)
    args = parser.parse_args()
    codex = args.codex.resolve(strict=True)
    summary = {"version": None, "model_calls": 0, "credential_used": False}
    with tempfile.TemporaryDirectory(prefix="laomedo-122-permissions-") as temporary:
        state = Path(temporary)
        home = state / "home"
        codex_home = state / "codex-home"
        project = state / "project"
        for path in (home, codex_home, project):
            path.mkdir()
        private_temp = state / "tmp"
        private_temp.mkdir()
        (project / "SKILL.md").write_text(
            "---\nname: fixture-122\ndescription: Synthetic.\n---\n\n"
            "Rule: answer amber.\n", encoding="utf-8")
        env = construct_env(home, codex_home, state, codex.parent)
        env["TEMP"] = env["TMP"] = str(private_temp)
        summary["version"] = codex_version(codex, env).splitlines()[0]
        server = AppServer(codex, project, env, state)
        try:
            ok, _ = server.initialize()
            summary["initialized"] = ok
            if not ok:
                return
            # Report only permission fields. The raw response may contain
            # local configuration, so it stays in the disposable temp root.
            for method, key in (("configRequirements/read", "requirements"),
                                ("config/read", "config")):
                response = server.send(method, {}, timeout=20)
                summary[key + "_available"] = "result" in response
                if "result" in response:
                    result = response["result"] or {}
                    if key == "requirements":
                        requirements = result.get("requirements") or result
                        summary["requirements_present"] = bool(
                            requirements.get("requirements"))
                        summary["allowed_sandbox_modes"] = requirements.get(
                            "allowedSandboxModes")
                        summary["allowed_approval_policies"] = requirements.get(
                            "allowedApprovalPolicies")
                    else:
                        config = result.get("config") or result
                        summary["configured_sandbox_mode"] = config.get("sandbox_mode")
                        summary["configured_approval_policy"] = config.get(
                            "approval_policy")
                else:
                    summary[key + "_error_code"] = (response.get("error") or {}).get(
                        "code")
            started = server.send("thread/start", {
                "cwd": str(project), "approvalPolicy": "never",
                "sandbox": "workspace-write",
            }, timeout=30)
            summary["thread_started"] = "result" in started
            if "result" in started:
                summary["effective_thread_sandbox"] = started["result"].get("sandbox")
                summary["instruction_source_count"] = len(
                    started["result"].get("instructionSources") or [])
            else:
                summary["thread_error_code"] = (started.get("error") or {}).get("code")
            canary = project / "canary.txt"
            executed = server.send("command/exec", {
                "command": [str(Path(env["SystemRoot"]) / "System32" / "cmd.exe"),
                            "/c", "echo synthetic > canary.txt"],
                "cwd": str(project),
                "sandboxPolicy": {"type": "workspaceWrite",
                                  "writableRoots": [str(project)],
                                  "networkAccess": False},
                "timeoutMs": 10000,
            }, timeout=20)
            summary["command_exec_response"] = "result" in executed
            summary["command_exec_exit_code"] = (executed.get("result") or {}).get(
                "exitCode")
            summary["canary_written"] = (
                canary.is_file() and
                canary.read_text(encoding="utf-8").strip() == "synthetic")
        except Exception as exc:
            summary["error_class"] = type(exc).__name__
        finally:
            summary["server_close"] = server.close()
            print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
