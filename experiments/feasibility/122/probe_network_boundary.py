"""Credential-free native Windows network boundary check for issue 122."""

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import sys
import tempfile
from threading import Thread

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "120"))
from _shared import AppServer, construct_env, inside_git_tree


class FixtureHandler(BaseHTTPRequestHandler):
    hits = 0

    def do_GET(self):
        type(self).hits += 1
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"laomedo-network-fixture-122")

    def log_message(self, *_args):
        pass


def execute(server, env: dict, draft: Path, url: str, network: bool) -> dict:
    before = FixtureHandler.hits
    response = server.send("command/exec", {
        "command": [str(Path(env["SystemRoot"]) / "System32" / "curl.exe"),
                    "--noproxy", "*", "-fsS", "--connect-timeout", "3",
                    "--max-time", "5", url],
        "cwd": str(draft),
        "sandboxPolicy": {"type": "workspaceWrite",
                          "writableRoots": [str(draft)],
                          "networkAccess": network},
        "timeoutMs": 15000,
    }, timeout=90)
    result = response.get("result") or {}
    return {"rpc_result": "result" in response,
            "exit_code": result.get("exitCode"),
            "fixture_response_seen": "laomedo-network-fixture-122" in
            result.get("stdout", ""),
            "server_hit": FixtureHandler.hits > before,
            "error_code": (response.get("error") or {}).get("code")}


def identity(server, env: dict, draft: Path, network: bool) -> dict:
    response = server.send("command/exec", {
        "command": [str(Path(env["SystemRoot"]) / "System32" / "whoami.exe"),
                    "/user", "/fo", "csv", "/nh"],
        "cwd": str(draft),
        "sandboxPolicy": {"type": "workspaceWrite",
                          "writableRoots": [str(draft)],
                          "networkAccess": network},
        "timeoutMs": 10000,
    }, timeout=30)
    result = response.get("result") or {}
    output = result.get("stdout", "")
    return {"rpc_result": "result" in response,
            "exit_code": result.get("exitCode"),
            "sandbox_user": ("offline" if "CodexSandboxOffline" in output else
                             "online" if "CodexSandboxOnline" in output else
                             "other_or_unknown")}


def external(server, env: dict, draft: Path, network: bool) -> dict:
    response = server.send("command/exec", {
        "command": [str(Path(env["SystemRoot"]) / "System32" / "curl.exe"),
                    "--noproxy", "*", "-fsS", "--connect-timeout", "3",
                    "--max-time", "7", "https://example.com/"],
        "cwd": str(draft),
        "sandboxPolicy": {"type": "workspaceWrite",
                          "writableRoots": [str(draft)],
                          "networkAccess": network},
        "timeoutMs": 10000,
    }, timeout=30)
    result = response.get("result") or {}
    return {"rpc_result": "result" in response,
            "exit_code": result.get("exitCode"),
            "stdout_nonempty": bool(result.get("stdout")),
            "error_code": (response.get("error") or {}).get("code")}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", required=True, type=Path)
    parser.add_argument("--profile-dir", type=Path)
    parser.add_argument("--state-dir", type=Path)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--identity-only", action="store_true")
    mode_group.add_argument("--loopback-only", action="store_true")
    parser.add_argument("--windows-mode", choices=("elevated", "unelevated"),
                        required=True)
    args = parser.parse_args()
    codex = args.codex.resolve(strict=True)
    if bool(args.profile_dir) != bool(args.state_dir):
        raise ValueError("profile_and_state_must_be_paired")
    private = bool(args.profile_dir)
    if private:
        profile = args.profile_dir.resolve(strict=True)
        log_state = args.state_dir.resolve(strict=True)
        if (profile.is_symlink() or log_state.is_symlink() or
                log_state != profile / "issue-122" or
                inside_git_tree(profile) or inside_git_tree(log_state)):
            raise ValueError("private_roots_invalid")
        parent = log_state / "runs"
    else:
        profile = None
        log_state = None
        parent = None
    repo = Path(__file__).resolve().parents[3]
    if not private:
        parent = (repo.parent / "probe-artifacts.local").resolve()
        if not parent.is_relative_to(repo.parent.resolve()):
            raise RuntimeError("scratch_parent_outside_workspace")
    parent.mkdir(exist_ok=True)
    fixture = HTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = Thread(target=fixture.serve_forever, daemon=True)
    thread.start()
    report = {"model_calls": 0, "credential_used": False,
              "config_file_changed": False,
              "tested_endpoint": "local_loopback_fixture",
              "reused_existing_private_profile": private,
              "requested_windows_mode": args.windows_mode}
    with tempfile.TemporaryDirectory(prefix="laomedo-122-network-", dir=parent,
                                     ignore_cleanup_errors=True) as scratch:
        state = Path(scratch)
        draft = state / "draft"
        home = (log_state / "home") if private else (state / "home")
        codex_home = (profile / "codex-home") if private else (state / "codex-home")
        environment_state = log_state if private else state
        for path in (draft, home, codex_home, environment_state / "appdata",
                     environment_state / "localappdata", environment_state / "tmp"):
            path.mkdir(exist_ok=True)
        env = construct_env(home, codex_home, environment_state, codex.parent)
        env["TEMP"] = env["TMP"] = str(environment_state / "tmp")
        url = f"http://127.0.0.1:{fixture.server_port}/fixture"
        server = AppServer(codex, draft, env, environment_state,
                           startup_args=["-c", f'windows.sandbox="{args.windows_mode}"'])
        try:
            ok, _ = server.initialize()
            report["initialized"] = ok
            if ok:
                config = server.send("config/read", {}, timeout=20)
                settings = (config.get("result") or {}).get("config") or {}
                report["configured_windows_sandbox"] = (
                    (settings.get("windows") or {}).get("sandbox"))
                if not args.identity_only:
                    report["phase"] = "network_enabled"
                    report["network_enabled"] = execute(server, env, draft, url, True)
                    report["phase"] = "network_disabled"
                    report["network_disabled"] = execute(server, env, draft, url, False)
                if not args.loopback_only:
                    report["phase"] = "identity_enabled"
                    report["identity_enabled"] = identity(server, env, draft, True)
                    report["phase"] = "identity_disabled"
                    report["identity_disabled"] = identity(server, env, draft, False)
                if not args.identity_only and not args.loopback_only:
                    report["phase"] = "external_enabled"
                    report["external_enabled"] = external(server, env, draft, True)
                    report["phase"] = "external_disabled"
                    report["external_disabled"] = external(server, env, draft, False)
                    report["network_boundary_passed"] = (
                        report["network_enabled"]["fixture_response_seen"] and
                        report["network_enabled"]["server_hit"] and
                        not report["network_disabled"]["fixture_response_seen"] and
                        not report["network_disabled"]["server_hit"] and
                        report["external_enabled"]["exit_code"] == 0 and
                        report["external_disabled"]["exit_code"] != 0)
                elif args.loopback_only:
                    report["loopback_blocked_when_disabled"] = (
                        not report["network_disabled"]["fixture_response_seen"] and
                        not report["network_disabled"]["server_hit"])
                report["phase"] = "complete"
        except Exception as exc:
            report["error_class"] = type(exc).__name__
        finally:
            server.close()
    report["scratch_retained"] = state.exists()
    fixture.shutdown()
    thread.join(timeout=5)
    fixture.server_close()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
