"""Two-container, credential-free Codex controller/executor isolation probe.

The controller gets a synthetic ACCESS_TOKEN and the executor does not. The
containers share a network namespace for a loopback, capability-authenticated
exec-server connection, but have separate process and mount namespaces. A fake
Responses stream requests one agent tool call, so no model turn is submitted.
Only nonsecret observations are printed.
"""

import argparse
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import tempfile
import threading
import time
from uuid import uuid4

from laomedo.local_runner import AppServer, IMAGE, VOLUME, _docker_prefix
from probe_mock_responses import MockResponses


PORT = 39871


def _docker(*args):
    response = subprocess.run(["docker", *args], capture_output=True, text=True,
                              timeout=30)
    if response.returncode:
        raise RuntimeError("docker_command_failed")
    return response.stdout.strip()


def _result(server, method, params, *, timeout=30):
    response = server.request(method, params, timeout=timeout)
    if "result" not in response or "error" in response:
        error = response.get("error") or {}
        code = error.get("code") if isinstance(error, dict) else None
        raise RuntimeError(f"rpc_rejected:{method}:{code}")
    return response["result"]


def probe(*, disconnect_executor=False, patch_target=None):
    controller_canary = "LAOMEDO_107_" + secrets.token_hex(24)
    executor_token = secrets.token_hex(32)
    executor_name = "laomedo-107-exec-" + uuid4().hex
    environment_id = "laomedo-107-" + uuid4().hex
    with tempfile.TemporaryDirectory(prefix="laomedo-107-remote-") as directory:
        root = Path(directory)
        for name in ("workspace", "canonical", "store"):
            (root / name).mkdir()
        workspace = root / "workspace"
        (workspace / "bundled-reader.sh").write_bytes((
            'if test -n "${ACCESS_TOKEN+x}"; then printf readable; '
            'else printf absent; fi > /draft/script-env.txt\n'
            "if tr '\\000' '\\n' </proc/1/environ | grep -q '^ACCESS_TOKEN='; "
            'then printf readable; else printf absent; fi > /draft/script-pid1.txt\n'
            'if test -r /home/runner/.codex/probe.secret; '
            'then printf readable; else printf absent; fi > /draft/script-file.txt\n'
        ).encode("utf-8"))
        executor = [
            "run", "--rm", "-d", "--name", executor_name, "--pull=never",
            "--network", "bridge", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--pids-limit", "128",
            "--memory", "1g", "--user", "10001:10001",
            "--mount", f"type=bind,source={workspace},target=/draft",
            "--tmpfs", "/home/runner/.codex:rw,uid=10001,gid=10001,mode=0700",
            "--workdir", "/draft", IMAGE, "codex", "exec-server",
            "--listen", f"ws://0.0.0.0:{PORT}",
            "--ws-auth", "capability-token", "--ws-token-sha256",
            hashlib.sha256(executor_token.encode()).hexdigest(),
        ]
        server = None
        marker = workspace / "agent-marker.txt"
        shell = (
            "sh -c 'if test -n \"${ACCESS_TOKEN+x}\"; then printf readable; "
            "else printf absent; fi > /draft/agent-env.txt; "
            "if tr \"\\000\" \"\\n\" </proc/1/environ | "
            "grep -q \"^ACCESS_TOKEN=\"; then printf readable; "
            "else printf absent; fi > /draft/agent-pid1.txt; "
            "sh /draft/bundled-reader.sh; "
            "printf executed > /draft/agent-marker.txt'"
        )
        if patch_target:
            target_path = ("/home/runner/.codex/patch-target.txt" if
                           patch_target == "controller" else
                           "/home/runner/.codex/executor-only.txt")
            patch = ("*** Begin Patch\n"
                     "*** Update File: " + target_path + "\n"
                     "@@\n-ORIGINAL\n+MUTATED\n*** End Patch")
            tool_input = ("const result = await tools.apply_patch(" +
                          json.dumps(patch) + "); text(result);")
        else:
            tool_input = ("const result = await tools.exec_command({cmd: " +
                          json.dumps(shell) + ", workdir: '/draft'}); " +
                          "text(result.exit_code);")
        try:
            _docker(*executor)
            _docker("exec", executor_name, "sh", "-c",
                    "printf ORIGINAL > /home/runner/.codex/executor-only.txt")
            prefix = _docker_prefix(workspace, root / "canonical", root / "store")
            prefix[prefix.index("--network") + 1] = "container:" + executor_name
            mount = f"type=volume,source={VOLUME},target=/home/runner/.codex"
            if mount not in prefix:
                raise RuntimeError("expected_login_volume_mount_missing")
            index = prefix.index(mount)
            if index == 0 or prefix[index - 1] != "--mount":
                raise RuntimeError("unexpected_login_volume_mount_shape")
            del prefix[index - 1:index + 1]
            insert = prefix.index("--workdir")
            prefix[insert:insert] = [
                "--tmpfs", "/home/runner/.codex:rw,uid=10001,gid=10001,mode=0700",
                "--env", "ACCESS_TOKEN=" + controller_canary,
            ]
            mock = MockResponses(tool_input=tool_input)
            mock.__enter__()
            prefix.extend([
                "-c", "features.deferred_executor=true",
                "-c", "features.executor_capability_discovery=true",
                "-c", 'model_provider="laomedo_mock"',
                "-c", 'model_providers.laomedo_mock.name="Laomedo Mock"',
                "-c", 'model_providers.laomedo_mock.base_url="' + mock.base_url + '"',
                "-c", 'model_providers.laomedo_mock.env_key="ACCESS_TOKEN"',
                "-c", 'model_providers.laomedo_mock.wire_api="responses"',
                "-c", 'model_providers.laomedo_mock.requires_openai_auth=false',
                "-c", 'model_providers.laomedo_mock.supports_websockets=false',
            ])
            server = AppServer(["docker", *prefix], root)
            _result(server, "initialize", {"clientInfo": {
                "name": "laomedo_107_probe", "title": "Laomedo 107 Probe",
                "version": "0.1.0"}, "capabilities": {"experimentalApi": True}})
            server.notify("initialized", {})
            _docker("exec", server.container_name, "sh", "-c",
                    "printf %s " + controller_canary +
                    " > /home/runner/.codex/probe.secret")
            _docker("exec", server.container_name, "sh", "-c",
                    "printf ORIGINAL > /home/runner/.codex/patch-target.txt")
            if _docker("exec", server.container_name, "sh", "-c",
                       "test -r /home/runner/.codex/probe.secret && "
                       "printf readable") != "readable":
                raise RuntimeError("controller_file_fixture_missing")
            _result(server, "environment/add", {
                "environmentId": environment_id,
                "execServerUrl": f"ws://127.0.0.1:{PORT}",
                "authBearerToken": executor_token,
                "connectTimeoutMs": 15000,
            }, timeout=25)
            deadline = time.monotonic() + 15
            status = {}
            while time.monotonic() < deadline:
                status = _result(server, "environment/status", {
                    "environmentId": environment_id})
                if status.get("status") != "pending":
                    break
                time.sleep(.2)
            if status.get("status") != "ready":
                raise RuntimeError("remote_environment_not_ready:" +
                                   str(status.get("status")) + ":" +
                                   str(status.get("error")))
            info = _result(server, "environment/info", {
                "environmentId": environment_id})
            direct = {
                "tool_environment": _docker("exec", executor_name, "sh", "-c",
                    'if test -n "${ACCESS_TOKEN+x}"; then printf readable; '
                    'else printf absent; fi'),
                "executor_pid1_environment": _docker("exec", executor_name,
                    "sh", "-c", "if tr '\\000' '\\n' </proc/1/environ | "
                    "grep -q '^ACCESS_TOKEN='; then printf readable; "
                    "else printf absent; fi"),
                "executor_credential_file": _docker("exec", executor_name,
                    "sh", "-c", "if test -r /home/runner/.codex/probe.secret; "
                    "then printf readable; else printf absent; fi"),
            }
            if set(direct.values()) - {"readable", "absent"}:
                raise RuntimeError("invalid_direct_probe_observation")
            if disconnect_executor:
                _docker("rm", "-f", executor_name)
            models = _result(server, "model/list", {}).get("data") or []
            if not models or not models[0].get("id"):
                raise RuntimeError("model_catalog_unavailable")
            thread = _result(server, "thread/start", {
                "model": models[0]["id"], "cwd": "/draft",
                "approvalPolicy": "never",
                "environments": [{"environmentId": environment_id,
                                  "cwd": "/draft"}],
            }).get("thread") or {}
            if not thread.get("id"):
                raise RuntimeError("thread_identity_missing")
            turn = _result(server, "turn/start", {
                "threadId": thread["id"], "model": models[0]["id"],
                "cwd": "/draft",
                "sandboxPolicy": {"type": "externalSandbox",
                                  "networkAccess": "restricted"},
                "environments": [{"environmentId": environment_id,
                                  "cwd": "/draft",
                                  "runtimeWorkspaceRoots": ["/draft"]}],
                "input": [{"type": "text",
                                            "text": "Synthetic fixture"}]})["turn"]["id"]
            turn_status, turn_error = server.wait_turn(
                turn, 30, threading.Event())
            observations = {}
            for name in ("agent-env.txt", "agent-pid1.txt",
                         "script-env.txt", "script-pid1.txt",
                         "script-file.txt"):
                path = workspace / name
                if path.exists():
                    observations[name] = path.read_text(encoding="utf-8")
            if set(observations.values()) - {"readable", "absent"}:
                raise RuntimeError("invalid_probe_observation")
            command_events = [event for event in server.events
                              if event.get("method") == "item/completed" and
                              ((event.get("params") or {}).get("item") or {})
                              .get("type") == "commandExecution"]
            no_fallback = not disconnect_executor or not marker.exists()
            if disconnect_executor and not no_fallback:
                raise RuntimeError("controller_fallback_after_executor_loss")
            controller_patch_content = _docker(
                "exec", server.container_name, "sh", "-c",
                "cat /home/runner/.codex/patch-target.txt")
            executor_patch_target = _docker(
                "exec", executor_name, "sh", "-c",
                "cat /home/runner/.codex/executor-only.txt") if not disconnect_executor else None
            if controller_patch_content not in {"ORIGINAL", "MUTATED"} or (
                    executor_patch_target not in {"ORIGINAL", "MUTATED", None}):
                raise RuntimeError("invalid_patch_target_observation")
            return {"schema_version": 1, "model_turns": 0,
                    "used_real_login_volume": False,
                    "separate_executor": True,
                    "remote_environment_status": status["status"],
                    "remote_shell": (info.get("shell") or {}).get("name"),
                    "direct_executor_canary_checks": direct,
                    "direct_process_separation_observed":
                        all(value == "absent" for value in direct.values()),
                    "synthetic_turn_status": turn_status,
                    "synthetic_turn_error_category": turn_error,
                    "mock_request_count": len(mock.requests),
                    "mock_tool_output_summary": [output.replace(
                        controller_canary, "[REDACTED]").replace(
                        executor_token, "[REDACTED]")[:500]
                        for request in mock.requests
                        for output in request["tool_outputs"]],
                    "agent_command_event_seen": bool(command_events),
                    "command_exit_codes": [((event.get("params") or {})
                                            .get("item") or {}).get("exitCode")
                                           for event in command_events],
                    "executor_disconnected_before_turn": disconnect_executor,
                    "no_controller_fallback_after_disconnect": no_fallback,
                    "patch_probe": patch_target,
                    "controller_only_file_modified":
                        controller_patch_content == "MUTATED",
                    "executor_only_file_modified":
                        executor_patch_target == "MUTATED",
                    "agent_command_boundary_verified": marker.exists() and
                        len(observations) == 5 and bool(command_events),
                    "tool_environment": observations.get("agent-env.txt"),
                    "executor_pid1_environment": observations.get(
                        "agent-pid1.txt"),
                    "bundled_script_environment": observations.get(
                        "script-env.txt"),
                    "bundled_script_pid1_environment": observations.get(
                        "script-pid1.txt"),
                    "bundled_script_credential_file": observations.get(
                        "script-file.txt"),
                    "controller_token_absent_from_executor":
                        len(observations) == 5 and all(
                            value == "absent" for value in observations.values())}
        finally:
            if server is not None:
                server.close()
            if "mock" in locals():
                mock.__exit__(None, None, None)
            subprocess.run(["docker", "rm", "-f", executor_name],
                           capture_output=True, timeout=15)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--disconnect-executor", action="store_true")
    parser.add_argument("--patch-probe", choices=("controller", "executor"))
    args = parser.parse_args()
    if args.disconnect_executor and args.patch_probe:
        parser.error("select one probe mode")
    result = probe(disconnect_executor=args.disconnect_executor,
                   patch_target=args.patch_probe)
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.disconnect_executor:
        if not result["no_controller_fallback_after_disconnect"]:
            raise SystemExit(1)
    elif args.patch_probe:
        if (result["controller_only_file_modified"] or
                result["executor_only_file_modified"] !=
                (args.patch_probe == "executor")):
            raise SystemExit(1)
    elif (not result["agent_command_boundary_verified"] or
          not result["controller_token_absent_from_executor"] or
          result["synthetic_turn_status"] != "completed"):
        raise SystemExit(1)
