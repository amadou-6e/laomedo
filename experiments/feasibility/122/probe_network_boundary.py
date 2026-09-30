"""Credential-free native Windows network boundary check for issue 122."""

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import sys
import tempfile
from threading import Thread

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "120"))
from _shared import AppServer, construct_env


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", required=True, type=Path)
    args = parser.parse_args()
    codex = args.codex.resolve(strict=True)
    repo = Path(__file__).resolve().parents[3]
    parent = (repo.parent / "probe-artifacts.local").resolve()
    if not parent.is_relative_to(repo.parent.resolve()):
        raise RuntimeError("scratch_parent_outside_workspace")
    parent.mkdir(exist_ok=True)
    fixture = HTTPServer(("127.0.0.1", 0), FixtureHandler)
    thread = Thread(target=fixture.serve_forever, daemon=True)
    thread.start()
    report = {"model_calls": 0, "credential_used": False,
              "config_file_changed": False,
              "tested_endpoint": "local_loopback_fixture"}
    with tempfile.TemporaryDirectory(prefix="laomedo-122-network-", dir=parent,
                                     ignore_cleanup_errors=True) as scratch:
        state = Path(scratch)
        draft = state / "draft"
        home = state / "home"
        codex_home = state / "codex-home"
        for path in (draft, home, codex_home, state / "appdata",
                     state / "localappdata", state / "tmp"):
            path.mkdir()
        env = construct_env(home, codex_home, state, codex.parent)
        env["TEMP"] = env["TMP"] = str(state / "tmp")
        url = f"http://127.0.0.1:{fixture.server_port}/fixture"
        server = AppServer(codex, draft, env, state,
                           startup_args=["-c", 'windows.sandbox="elevated"'])
        try:
            ok, _ = server.initialize()
            report["initialized"] = ok
            if ok:
                report["phase"] = "network_enabled"
                report["network_enabled"] = execute(server, env, draft, url, True)
                report["phase"] = "network_disabled"
                report["network_disabled"] = execute(server, env, draft, url, False)
                report["network_boundary_passed"] = (
                    report["network_enabled"]["fixture_response_seen"] and
                    report["network_enabled"]["server_hit"] and
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
