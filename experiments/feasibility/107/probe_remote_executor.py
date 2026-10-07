"""Two-container, credential-free Codex controller/executor isolation probe.

The controller gets a synthetic ACCESS_TOKEN and the executor does not. The
containers share a network namespace for a loopback, capability-authenticated
exec-server connection, but have separate process and mount namespaces. A fake
Responses stream requests one agent tool call, so no model turn is submitted.
Only nonsecret observations are printed.
"""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
import threading
import time
from uuid import uuid4

from laomedo.local_runner import (AppServer, CLI_VERSION, IMAGE, IMAGE_ID,
                                  VOLUME, _docker_prefix)
from probe_mock_responses import MockResponses


PORT = 39871
EXPECTED_TOOLS = frozenset({
    "apply_patch", "clock__curr_time", "create_goal", "exec_command",
    "get_goal", "update_goal", "view_image", "wait_for_environment",
    "write_stdin",
})


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


def _code_mode_tools(requests):
    for request in requests:
        for output in request["tool_outputs"]:
            try:
                blocks = ast.literal_eval(output)
            except (SyntaxError, ValueError):
                continue
            if not isinstance(blocks, list):
                continue
            for block in blocks:
                value = block.get("text") if isinstance(block, dict) else None
                if isinstance(value, str) and value.startswith("TOOLS:"):
                    names = json.loads(value[6:])
                    if isinstance(names, list) and all(
                            isinstance(name, str) for name in names):
                        return names
    return []


def _resumed_tool_evidence(requests):
    """Identify the output added by turn two, rather than replayed history."""
    if len(requests) != 4:
        return [], False
    first_outputs = requests[1]["tool_outputs"]
    resumed_input = requests[2]["tool_outputs"]
    final_outputs = requests[3]["tool_outputs"]
    history_retained = bool(first_outputs) and all(
        output in resumed_input for output in first_outputs)
    if not history_retained or len(final_outputs) != len(resumed_input) + 1:
        return [], history_retained
    return _code_mode_tools([{"tool_outputs": [final_outputs[-1]]}]), history_retained


def _controller_socket_inodes(name):
    links = _docker("exec", name, "sh", "-c",
                    'for fd in /proc/[0-9]*/fd/*; do '
                    'readlink "$fd" 2>/dev/null || :; done')
    return set(re.findall(r"socket:\[(\d+)\]", links))


def _controller_listeners(name):
    """Match listening sockets to processes visible in the controller PID namespace."""
    owned = _controller_socket_inodes(name)
    if not owned:
        return []
    listeners = []
    tcp = _docker("exec", name, "sh", "-c",
                  "cat /proc/net/tcp /proc/net/tcp6 2>/dev/null")
    for line in tcp.splitlines():
        fields = line.split()
        if len(fields) > 9 and fields[3] == "0A" and fields[9] in owned:
            listeners.append("tcp")
    unix = _docker("exec", name, "cat", "/proc/net/unix")
    for line in unix.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 7 or fields[6] not in owned:
            continue
        flags = int(fields[3], 16)
        path = fields[7] if len(fields) > 7 else ""
        if flags & 0x10000 or path.startswith("@"):
            listeners.append("unix")
    return sorted(set(listeners))


def _controller_has_abstract_listener(name, socket_name):
    owned = _controller_socket_inodes(name)
    unix = _docker("exec", name, "cat", "/proc/net/unix")
    return any(len(fields) > 7 and fields[6] in owned and
               fields[7] == "@" + socket_name and int(fields[3], 16) & 0x10000
               for fields in (line.split() for line in unix.splitlines()[1:]))


def _require_no_controller_listener(name):
    listeners = _controller_listeners(name)
    if listeners:
        raise RuntimeError("controller_listener_gate_failed")
    return listeners


def probe(*, disconnect_executor=False, patch_target=None,
          listener_probe=False, restart_controller=False):
    controller_canary = "LAOMEDO_107_" + secrets.token_hex(24)
    executor_token = secrets.token_hex(32)
    executor_name = "laomedo-107-exec-" + uuid4().hex
    init_name = "laomedo-107-init-" + uuid4().hex
    environment_id = "laomedo-107-" + uuid4().hex
    controller_volume = "laomedo-107-controller-" + uuid4().hex
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
        controller_volume_requested = False
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
        tool_list_output = ("text('TOOLS:' + JSON.stringify("
                            "ALL_TOOLS.map(tool => tool.name).sort()));")
        if patch_target:
            target_path = ("/home/runner/.codex/patch-target.txt" if
                           patch_target == "controller" else
                           "/home/runner/.codex/executor-only.txt")
            patch = ("*** Begin Patch\n"
                     "*** Update File: " + target_path + "\n"
                     "@@\n-ORIGINAL\n+MUTATED\n*** End Patch")
            tool_input = ("const result = await tools.apply_patch(" +
                          json.dumps(patch) + "); text(result); " +
                          tool_list_output)
        else:
            tool_input = ("const result = await tools.exec_command({cmd: " +
                          json.dumps(shell) + ", workdir: '/draft'}); " +
                          "text(result.exit_code); " + tool_list_output)
        try:
            if _docker("image", "inspect", IMAGE, "--format", "{{.Id}}") != IMAGE_ID:
                raise RuntimeError("image_digest_changed")
            if restart_controller:
                controller_volume_requested = True
                _docker("volume", "create", controller_volume)
                _docker("run", "--rm", "--name", init_name,
                        "--pull=never", "--network", "none",
                        "--user", "0:0", "--cap-drop", "ALL",
                        "--cap-add", "CHOWN", "--mount",
                        "type=volume,source=" + controller_volume +
                        ",target=/home/runner/.codex", IMAGE,
                        "chown", "10001:10001", "/home/runner/.codex")
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
            controller_home = (["--mount", "type=volume,source=" +
                                controller_volume + ",target=/home/runner/.codex"]
                               if restart_controller else
                               ["--tmpfs", "/home/runner/.codex:rw,uid=10001,gid=10001,mode=0700"])
            prefix[insert:insert] = controller_home + [
                "--env", "ACCESS_TOKEN=" + controller_canary]
            executor_loss_at = []
            def drop_executor():
                _docker("rm", "-f", executor_name)
                executor_loss_at.append(time.monotonic())

            mock = MockResponses(
                tool_input=tool_input,
                before_first_output=drop_executor if disconnect_executor else None,
                tool_request_numbers=(1, 3) if restart_controller else (1,))
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
            observed_cli_version = _docker("exec", server.container_name,
                                           "codex", "--version")
            if observed_cli_version != CLI_VERSION:
                raise RuntimeError("unsupported_codex_cli_version")
            _docker("exec", server.container_name, "sh", "-c",
                    "printf %s " + controller_canary +
                    " > /home/runner/.codex/probe.secret")
            _docker("exec", server.container_name, "sh", "-c",
                    "printf ORIGINAL > /home/runner/.codex/patch-target.txt")
            initial_listeners = _require_no_controller_listener(server.container_name)
            if listener_probe:
                _docker("exec", "-d", server.container_name,
                        "codex", "exec-server", "--listen",
                        "ws://127.0.0.1:39872")
                deadline = time.monotonic() + 5
                injected_listeners = []
                while time.monotonic() < deadline:
                    injected_listeners = _controller_listeners(
                        server.container_name)
                    if "tcp" in injected_listeners:
                        break
                    time.sleep(.1)
                if injected_listeners != ["tcp"]:
                    raise RuntimeError("tcp_listener_negative_control_ambiguous")
                abstract_name = "laomedo-107-" + uuid4().hex
                script = ("require('node:net').createServer().listen('\\0" +
                          abstract_name + "'); setInterval(() => {}, 1000)")
                _docker("exec", "-d", server.container_name,
                        "node", "-e", script)
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    injected_listeners = _controller_listeners(
                        server.container_name)
                    if _controller_has_abstract_listener(
                            server.container_name, abstract_name):
                        break
                    time.sleep(.1)
                expected_abstract_listener_seen = _controller_has_abstract_listener(
                    server.container_name, abstract_name)
                injected_listeners = _controller_listeners(server.container_name)
                gate_refused = False
                try:
                    _require_no_controller_listener(server.container_name)
                except RuntimeError as exc:
                    if str(exc) != "controller_listener_gate_failed":
                        raise
                    gate_refused = True
                return {"schema_version": 1, "model_turns": 0,
                        "used_real_login_volume": False,
                        "controller_listeners_before": initial_listeners,
                        "injected_listener_detected":
                            set(injected_listeners) == {"tcp", "unix"} and
                            expected_abstract_listener_seen,
                        "gate_refused_injected_listeners": gate_refused,
                        "injected_listener_types": injected_listeners}
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
            started = time.monotonic()
            turn_status, turn_error = server.wait_turn(
                turn, 5 if disconnect_executor else 30,
                threading.Event())
            first_turn_status = turn_status
            resumed_thread_id = None
            if restart_controller:
                if first_turn_status != "completed":
                    raise RuntimeError("first_turn_incomplete_before_restart")
                server.close()
                server = None
                for name in ("agent-env.txt", "agent-pid1.txt",
                             "script-env.txt", "script-pid1.txt",
                             "script-file.txt", "agent-marker.txt"):
                    (workspace / name).unlink(missing_ok=True)
                server = AppServer(["docker", *prefix], root)
                _result(server, "initialize", {"clientInfo": {
                    "name": "laomedo_107_probe", "title": "Laomedo 107 Probe",
                    "version": "0.1.0"}, "capabilities": {"experimentalApi": True}})
                server.notify("initialized", {})
                if _docker("exec", server.container_name,
                           "codex", "--version") != CLI_VERSION:
                    raise RuntimeError("unsupported_codex_cli_version")
                _require_no_controller_listener(server.container_name)
                _result(server, "environment/add", {
                    "environmentId": environment_id,
                    "execServerUrl": f"ws://127.0.0.1:{PORT}",
                    "authBearerToken": executor_token,
                    "connectTimeoutMs": 15000,
                }, timeout=25)
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    status = _result(server, "environment/status", {
                        "environmentId": environment_id})
                    if status.get("status") != "pending":
                        break
                    time.sleep(.2)
                if status.get("status") != "ready":
                    raise RuntimeError("remote_environment_not_ready_after_restart")
                resumed = _result(server, "thread/resume", {
                    "threadId": thread["id"], "cwd": "/draft",
                    "environments": [{"environmentId": environment_id,
                                      "cwd": "/draft"}],
                }).get("thread") or {}
                resumed_thread_id = resumed.get("id")
                if resumed_thread_id != thread["id"]:
                    raise RuntimeError("resumed_thread_identity_mismatch")
                second_turn = _result(server, "turn/start", {
                    "threadId": resumed_thread_id,
                    "model": models[0]["id"], "cwd": "/draft",
                    "sandboxPolicy": {"type": "externalSandbox",
                                      "networkAccess": "restricted"},
                    "environments": [{"environmentId": environment_id,
                                      "cwd": "/draft",
                                      "runtimeWorkspaceRoots": ["/draft"]}],
                    "input": [{"type": "text", "text": "Synthetic restart fixture"}],
                })["turn"]["id"]
                turn_status, turn_error = server.wait_turn(
                    second_turn, 30, threading.Event())
            elapsed_seconds = round(time.monotonic() - started, 2)
            executor_loss_to_turn_end = (round(time.monotonic() -
                                         executor_loss_at[0], 2)
                                         if executor_loss_at else None)
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
            if restart_controller:
                resumed_tools, history_retained = _resumed_tool_evidence(
                    mock.requests)
                code_mode_tools = set(resumed_tools)
            else:
                history_retained = None
                code_mode_tools = set(_code_mode_tools(mock.requests))
            tool_surface_exact = (code_mode_tools == EXPECTED_TOOLS
                                  if code_mode_tools else None)
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
                    "controller_listeners_before": initial_listeners,
                    "cli_version_exact": observed_cli_version == CLI_VERSION,
                    "image_id_exact": True,
                    "code_mode_tools": sorted(code_mode_tools),
                    "tool_surface_exact": tool_surface_exact,
                    "command_event_keys": [sorted(
                        ((event.get("params") or {}).get("item") or {}))
                        for event in command_events],
                    "direct_executor_canary_checks": direct,
                    "direct_process_separation_observed":
                        all(value == "absent" for value in direct.values()),
                    "synthetic_turn_status": turn_status,
                    "first_turn_status": first_turn_status,
                    "controller_restarted": restart_controller,
                    "resumed_thread_id_matches":
                        resumed_thread_id == thread["id"] if restart_controller else None,
                    "resumed_history_retained": history_retained,
                    "synthetic_turn_error_category": turn_error,
                    "turn_wait_seconds": elapsed_seconds,
                    "executor_loss_to_turn_end_seconds":
                        executor_loss_to_turn_end,
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
                    "executor_disconnected_during_turn": disconnect_executor,
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
                        (all(value == "absent" for value in observations.values())
                         if len(observations) == 5 else None)}
        finally:
            try:
                if server is not None:
                    server.close()
            finally:
                try:
                    if "mock" in locals():
                        mock.__exit__(None, None, None)
                finally:
                    subprocess.run(["docker", "rm", "-f", init_name],
                                   capture_output=True, timeout=15)
                    subprocess.run(["docker", "rm", "-f", executor_name],
                                   capture_output=True, timeout=15)
                    if controller_volume_requested:
                        inspected = subprocess.run(
                            ["docker", "volume", "inspect", controller_volume],
                            capture_output=True, timeout=15)
                        if inspected.returncode == 0:
                            removed = subprocess.run(
                                ["docker", "volume", "rm", controller_volume],
                                capture_output=True, timeout=15)
                            if removed.returncode:
                                raise RuntimeError("controller_volume_cleanup_failed")
                        elif b"No such volume" not in inspected.stderr:
                            raise RuntimeError("controller_volume_cleanup_unverified")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--disconnect-executor", action="store_true")
    parser.add_argument("--patch-probe", choices=("controller", "executor"))
    parser.add_argument("--listener-probe", action="store_true")
    parser.add_argument("--restart-probe", action="store_true")
    args = parser.parse_args()
    if sum(bool(value) for value in (args.disconnect_executor,
                                     args.patch_probe,
                                     args.listener_probe,
                                     args.restart_probe)) > 1:
        parser.error("select one probe mode")
    result = probe(disconnect_executor=args.disconnect_executor,
                   patch_target=args.patch_probe,
                   listener_probe=args.listener_probe,
                   restart_controller=args.restart_probe)
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.listener_probe:
        if (not result["injected_listener_detected"] or
                not result["gate_refused_injected_listeners"]):
            raise SystemExit(1)
    elif args.disconnect_executor:
        if (not result["no_controller_fallback_after_disconnect"] or
                result["executor_loss_to_turn_end_seconds"] is None or
                result["executor_loss_to_turn_end_seconds"] > 8):
            raise SystemExit(1)
    elif args.restart_probe:
        if (result["first_turn_status"] != "completed" or
                result["synthetic_turn_status"] != "completed" or
                not result["resumed_thread_id_matches"] or
                not result["resumed_history_retained"] or
                not result["agent_command_boundary_verified"] or
                not result["controller_token_absent_from_executor"] or
                not result["tool_surface_exact"] or
                result["mock_request_count"] != 4):
            raise SystemExit(1)
    elif args.patch_probe:
        if (result["controller_only_file_modified"] or
                result["executor_only_file_modified"] !=
                (args.patch_probe == "executor") or
                not result["tool_surface_exact"]):
            raise SystemExit(1)
    elif (not result["agent_command_boundary_verified"] or
          not result["controller_token_absent_from_executor"] or
          not result["tool_surface_exact"] or
          result["synthetic_turn_status"] != "completed"):
        raise SystemExit(1)
