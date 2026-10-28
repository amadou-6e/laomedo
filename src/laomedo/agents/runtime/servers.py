"""Own native app-server processes and the split-controller boundary."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4
import hashlib
import json
import laomedo.agents.contracts.output as _contracts_output
import laomedo.agents.runtime.settings as _runtime_settings
import laomedo.agents.runtime.errors as _runtime_errors
import laomedo.agents.runtime.utils as _runtime_utils
import laomedo.host.leases.settings as _leases_settings
import laomedo.host.leases.models as _leases_models
import laomedo.host.leases.utils as _leases_utils
import os
import laomedo.activity.runner.settings as _runner_settings
import queue
import re
import secrets
import subprocess
import threading
import time


class AppServer:
    def __init__(
        self, command: list[str], evidence: Path, *, env=None, secret_redactions=()
    ):
        self.telemetry = None
        if _runner_settings.Settings().otel == "1":
            import laomedo.activity.runner.telemetry as _runner_telemetry

            self.telemetry = _runner_telemetry.LaunchTelemetry(evidence)
            index = command.index("app-server")
            command = command[:index] + self.telemetry.arguments() + command[index:]
        if _runtime_settings.Settings().multi_agent == "1":
            index = command.index("app-server")
            command = (
                command[:index]
                + [
                    "--disable",
                    "memories",
                    "-c",
                    "features.multi_agent=true",
                    "-c",
                    "agents.max_threads=2",
                    "-c",
                    "agents.max_depth=1",
                ]
                + command[index:]
            )
        self.events = []
        self.messages = queue.Queue()
        self.container_name = command[command.index("--name") + 1]
        self.run_id = None
        self.launch_token = None
        for value in (
            command[index + 1]
            for index, item in enumerate(command[:-1])
            if item == "--label"
        ):
            if value.startswith(_leases_settings.LABEL_RUN + "="):
                self.run_id = value.split("=", 1)[1]
            elif value.startswith(_leases_settings.LABEL_TOKEN + "="):
                self.launch_token = value.split("=", 1)[1]
        self.active_thread_id = None
        self.interrupt_acknowledged = False
        self.secret_redactions = tuple(
            value for value in secret_redactions if value
        ) + ((self.telemetry.token,) if self.telemetry else ())
        self.native_completion_status = None
        self.log = (evidence / "raw-events.jsonl").open("a", encoding="utf-8")
        self.activity_log = (evidence / "activity-events.jsonl").open(
            "a", encoding="utf-8"
        )
        self.stderr = (evidence / "stderr.log").open("a", encoding="utf-8")
        try:
            self.process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                env=env,
            )
        except Exception:
            if self.telemetry:
                self.telemetry.close()
            self.log.close()
            self.activity_log.close()
            self.stderr.close()
            raise
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.stderr_reader = threading.Thread(target=self._read_stderr, daemon=True)
        self.reader.start()
        self.stderr_reader.start()
        self.seq = 0

    def _redact(self, line: str) -> str:
        for secret in self.secret_redactions:
            line = line.replace(secret, "[REDACTED_RUN_CAPABILITY]")
        return line

    def _read(self):
        for line in self.process.stdout:
            line = self._redact(line)
            self.log.write(line)
            self.log.flush()
            try:
                event = json.loads(line)
                import laomedo.activity.runner.feed as _runner_feed

                if _runner_feed.notification(event):
                    self.activity_log.write(
                        json.dumps(_runner_feed.receipt(event), ensure_ascii=False)
                        + "\n"
                    )
                    self.activity_log.flush()
                self.messages.put(event)
            except json.JSONDecodeError:
                self.events.append({"method": "invalid/json"})

    def _read_stderr(self):
        for line in self.process.stderr:
            self.stderr.write(self._redact(line))
            self.stderr.flush()

    def request(self, method: str, params: dict, timeout: float = 30) -> dict:
        self.seq += 1
        request_id = self.seq
        self.process.stdin.write(
            json.dumps({"id": request_id, "method": method, "params": params}) + "\n"
        )
        self.process.stdin.flush()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                msg = self.messages.get(timeout=min(0.5, deadline - time.monotonic()))
            except queue.Empty:
                if self.process.poll() is not None:
                    raise _runtime_errors.RunnerError("app_server_exited")
                continue
            if msg.get("id") == request_id and "method" not in msg:
                return msg
            self._observe(msg)
        raise _runtime_errors.RunnerError("request_timeout:" + method)

    def notify(self, method: str, params: dict) -> None:
        self.process.stdin.write(
            json.dumps({"method": method, "params": params}) + "\n"
        )
        self.process.stdin.flush()

    def _observe(self, msg):
        self.events.append(msg)
        reference = getattr(self, "output_requirements", None)
        if (
            reference is not None
            and msg.get("method") == "item/tool/call"
            and "id" in msg
        ):
            params = msg.get("params") or {}
            response = _contracts_output.precheck_response(
                reference, params, self.active_thread_id
            )
            if (
                params.get("tool") == "laomedo_output_precheck"
                and params.get("namespace") is None
                and params.get("threadId") == self.active_thread_id
            ):
                self.precheck_call_count = getattr(self, "precheck_call_count", 0) + 1
                result = json.loads(response["contentItems"][0]["text"])
                if not any(
                    error["code"] == "precheck_binding_mismatch"
                    for error in result["errors"]
                ):
                    calls = getattr(self, "verified_precheck_calls", set())
                    if isinstance(params.get("callId"), str):
                        calls.add(params["callId"])
                    self.verified_precheck_calls = calls
            self.process.stdin.write(
                json.dumps({"id": msg["id"], "result": response}) + "\n"
            )
            self.process.stdin.flush()

    def wait_turn(
        self, turn_id: str, timeout: float, cancelled: threading.Event
    ) -> tuple[str, str | None]:
        deadline = time.monotonic() + timeout
        cursor = 0
        interrupt_sent = False
        while time.monotonic() < deadline:
            for event in self.events[cursor:]:
                if event.get("method") == "turn/completed":
                    turn = event.get("params", {}).get("turn") or {}
                    if turn.get("id") == turn_id:
                        self.native_completion_status = turn.get("status") or "unknown"
                        if (
                            interrupt_sent
                            and self.native_completion_status == "interrupted"
                        ):
                            return "cancelled", "cancelled_by_user"
                        return self.native_completion_status, None
            cursor = len(self.events)
            if cancelled.is_set() and not interrupt_sent:
                self.interrupt(turn_id)
                interrupt_sent = True
                deadline = min(deadline, time.monotonic() + 5)
            try:
                msg = self.messages.get(timeout=min(0.25, deadline - time.monotonic()))
            except queue.Empty:
                if self.process.poll() is not None:
                    return (
                        ("cancelled", "cancel_native_unconfirmed")
                        if interrupt_sent
                        else ("failed", "app_server_exited")
                    )
                continue
            self._observe(msg)
        if interrupt_sent:
            return "cancelled", "cancel_native_unconfirmed"
        self.interrupt(turn_id)
        return "timeout", "turn_timeout"

    def interrupt(self, turn_id: str) -> None:
        if not self.active_thread_id:
            return
        try:
            response = self.request(
                "turn/interrupt",
                {"threadId": self.active_thread_id, "turnId": turn_id},
                timeout=5,
            )
            self.interrupt_acknowledged = (
                "result" in response and "error" not in response
            )
        except (_runtime_errors.RunnerError, OSError, ValueError):
            # Forced container removal below remains the authoritative boundary.
            self.interrupt_acknowledged = False

    def close(self) -> None:
        verified = False
        exact = (
            getattr(self, "run_id", None) is not None
            and getattr(self, "launch_token", None) is not None
        )
        try:
            # Stop the owned container promptly, then repeat after the docker
            # client exits to close the startup race before the first removal.
            try:
                if exact:
                    _leases_utils.cleanup_exact(
                        _leases_models.ContainerIdentity(
                            name=self.container_name,
                            run_id=self.run_id,
                            token=self.launch_token,
                        )
                    )
                else:
                    subprocess.run(
                        ["docker", "rm", "-f", self.container_name],
                        capture_output=True,
                        timeout=15,
                    )
            except (OSError, subprocess.TimeoutExpired):
                pass
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            try:
                if exact:
                    verified, _ = _leases_utils.cleanup_exact(
                        _leases_models.ContainerIdentity(
                            name=self.container_name,
                            run_id=self.run_id,
                            token=self.launch_token,
                        )
                    )
                else:
                    subprocess.run(
                        ["docker", "rm", "-f", self.container_name],
                        capture_output=True,
                        timeout=15,
                    )
                    probe = subprocess.run(
                        ["docker", "inspect", self.container_name],
                        capture_output=True,
                        timeout=10,
                    )
                    stderr = probe.stderr or b""
                    if isinstance(stderr, str):
                        stderr = stderr.encode()
                    verified = probe.returncode != 0 and (
                        b"no such object:" in stderr.lower()
                        or b"no such container:" in stderr.lower()
                    )
            except (OSError, subprocess.TimeoutExpired):
                verified = False
        finally:
            self.reader.join(timeout=5)
            self.stderr_reader.join(timeout=5)
            self.log.close()
            self.activity_log.close()
            if self.telemetry:
                self.telemetry.close()
            self.stderr.close()
        if not verified:
            raise _runtime_errors.RunnerError("container_termination_unverified")


class SplitAppServer(AppServer):
    """Pinned Codex controller with a separate, disposable tool executor.

    This mode is credential-free until the app-owned OAuth broker is connected.
    The executor never mounts the controller profile or receives ACCESS_TOKEN.
    """

    def __init__(
        self,
        workspace: Path,
        canonical: Path,
        store_mount: Path,
        evidence: Path,
        profile: str,
        *,
        provider_config=(),
        access_token=None,
    ):
        self.executor_name = "laomedo-executor-" + uuid4().hex
        self.environment_id = "laomedo-executor-" + uuid4().hex
        self.executor_token = secrets.token_hex(32)
        self.registered = False
        self.authorization_probe = None
        self._controller_started = False
        self._executor_started = False
        if (
            _runtime_utils._docker_checked(
                "image", "inspect", _runtime_settings.IMAGE, "--format", "{{.Id}}"
            )
            != _runtime_settings.IMAGE_ID
        ):
            raise _runtime_errors.RunnerError("docker_image_digest_changed")
        executor = [
            "run",
            "--rm",
            "-d",
            "--name",
            self.executor_name,
            "--pull=never",
            "--network",
            "bridge",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "128",
            "--memory",
            "1g",
            "--user",
            "10001:10001",
            "--mount",
            f"type=bind,source={workspace},target=/draft",
            "--tmpfs",
            "/home/runner/.codex:rw,uid=10001,gid=10001,mode=0700",
            "--workdir",
            "/draft",
            _runtime_settings.IMAGE,
            "codex",
            "exec-server",
            "--listen",
            "ws://0.0.0.0:39871",
            "--ws-auth",
            "capability-token",
            "--ws-token-sha256",
            hashlib.sha256(self.executor_token.encode()).hexdigest(),
        ]
        try:
            _runtime_utils._docker_checked(*executor, timeout=30)
            self._executor_started = True
            command = _runtime_utils._docker_prefix(
                workspace, canonical, store_mount, nested_sandbox=False
            )
            command[command.index("--network") + 1] = "container:" + self.executor_name
            old_mount = f"type=volume,source={_runtime_settings.VOLUME},target=/home/runner/.codex"
            index = command.index(old_mount)
            del command[index - 1 : index + 1]
            command[command.index("--workdir") : command.index("--workdir")] = [
                "--mount",
                f"type=volume,source={profile},target=/home/runner/.codex",
            ]
            command += [
                "-c",
                "features.deferred_executor=true",
                "-c",
                "features.executor_capability_discovery=true",
            ]
            for setting in provider_config:
                command += ["-c", setting]
            environment = None
            if access_token is not None:
                if not isinstance(access_token, str) or not access_token:
                    raise _runtime_errors.RunnerError("invalid_controller_token")
                command[command.index("--workdir") : command.index("--workdir")] = [
                    "--env",
                    "ACCESS_TOKEN",
                ]
                environment = dict(os.environ, ACCESS_TOKEN=access_token)
            super().__init__(["docker", *command], evidence, env=environment)
            self._controller_started = True
        except Exception:
            if self._executor_started:
                subprocess.run(
                    ["docker", "rm", "-f", self.executor_name],
                    capture_output=True,
                    timeout=15,
                )
            raise

    def _controller_listeners(self) -> set[str]:
        """Reject controller-owned listening TCP/Unix and any UDP socket."""
        fds = _runtime_utils._docker_checked(
            "exec",
            self.container_name,
            "sh",
            "-c",
            "ls -l /proc/[0-9]*/fd 2>/dev/null",
            timeout=5,
        )
        owned = set(re.findall(r"socket:\[(\d+)\]", fds))
        if not owned:
            return set()
        found = set()
        for table, kind in (
            ("tcp", "tcp"),
            ("tcp6", "tcp"),
            ("udp", "udp"),
            ("udp6", "udp"),
        ):
            rows = _runtime_utils._docker_checked(
                "exec", self.container_name, "cat", "/proc/net/" + table, timeout=5
            )
            for row in rows.splitlines()[1:]:
                fields = row.split()
                if (
                    len(fields) > 9
                    and fields[9] in owned
                    and (kind == "udp" or fields[3] == "0A")
                ):
                    found.add(kind)
        rows = _runtime_utils._docker_checked(
            "exec", self.container_name, "cat", "/proc/net/unix", timeout=5
        )
        for row in rows.splitlines()[1:]:
            fields = row.split()
            if len(fields) > 6 and fields[6] in owned and int(fields[3], 16) & 0x10000:
                found.add("unix")
        return found

    def assert_controller_isolated(self) -> None:
        if self._controller_listeners():
            raise _runtime_errors.RunnerError("controller_listener_gate_failed")
        if (
            _runtime_utils._docker_checked(
                "exec", self.container_name, "codex", "--version", timeout=5
            )
            != _runtime_settings.CLI_VERSION
        ):
            raise _runtime_errors.RunnerError("unsupported_codex_cli_version")
        if (
            _runtime_utils._docker_checked(
                "inspect",
                self.executor_name,
                "--format",
                "{{.State.Running}}",
                timeout=5,
            )
            != "true"
        ):
            raise _runtime_errors.RunnerError("executor_not_running")
        for name in (self.container_name, self.executor_name):
            if (
                _runtime_utils._docker_checked(
                    "inspect", name, "--format", "{{.Image}}", timeout=5
                )
                != _runtime_settings.IMAGE_ID
            ):
                raise _runtime_errors.RunnerError("running_image_digest_changed")

    def register_executor(self) -> None:
        self.assert_controller_isolated()
        response = self.request(
            "environment/add",
            {
                "environmentId": self.environment_id,
                "execServerUrl": "ws://127.0.0.1:39871",
                "authBearerToken": self.executor_token,
                "connectTimeoutMs": 15000,
            },
            timeout=25,
        )
        if "result" not in response or "error" in response:
            raise _runtime_errors.RunnerError("executor_registration_rejected")
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            response = self.request(
                "environment/status", {"environmentId": self.environment_id}, timeout=5
            )
            status = (response.get("result") or {}).get("status")
            if status == "ready":
                self.registered = True
                return
            if status != "pending":
                break
            time.sleep(0.2)
        raise _runtime_errors.RunnerError("executor_not_ready")

    def thread_environment(self) -> list[dict]:
        if not self.registered:
            raise _runtime_errors.RunnerError("executor_not_registered")
        selection = [{"environmentId": self.environment_id, "cwd": "/draft"}]
        self.assert_executor_selection(selection)
        return selection

    def turn_environment(self) -> list[dict]:
        if not self.registered:
            raise _runtime_errors.RunnerError("executor_not_registered")
        selection = [
            {
                "environmentId": self.environment_id,
                "cwd": "/draft",
                "runtimeWorkspaceRoots": ["/draft"],
            }
        ]
        self.assert_executor_selection(selection)
        return selection

    def assert_executor_selection(self, selection: list[dict]) -> None:
        """Refuse a missing or ambiguous remote tool route before dispatch."""
        if (
            len(selection) != 1
            or selection[0].get("environmentId") != self.environment_id
            or selection[0].get("cwd") != "/draft"
        ):
            raise _runtime_errors.RunnerError("executor_selection_mismatch")

    def wait_turn(
        self, turn_id: str, timeout: float, cancelled: threading.Event
    ) -> tuple[str, str | None]:
        deadline = time.monotonic() + timeout
        cursor = 0
        while time.monotonic() < deadline:
            for event in self.events[cursor:]:
                if event.get("method") == "turn/completed":
                    turn = event.get("params", {}).get("turn") or {}
                    if turn.get("id") == turn_id:
                        return turn.get("status") or "unknown", None
            cursor = len(self.events)
            if cancelled.is_set():
                self.interrupt(turn_id)
                return "cancelled", "cancelled_by_user"
            if self.authorization_probe is not None and not self.authorization_probe():
                self.interrupt(turn_id)
                return "unknown", "auth_revoked_during_turn"
            try:
                if (
                    _runtime_utils._docker_checked(
                        "inspect",
                        self.executor_name,
                        "--format",
                        "{{.State.Running}}",
                        timeout=3,
                    )
                    != "true"
                ):
                    return "unknown", "executor_lost"
            except _runtime_errors.RunnerError:
                return "unknown", "executor_lost"
            try:
                msg = self.messages.get(timeout=min(0.25, deadline - time.monotonic()))
            except queue.Empty:
                if self.process.poll() is not None:
                    return "unknown", "controller_exited"
                continue
            self._observe(msg)
        self.interrupt(turn_id)
        return "timeout", "turn_timeout"

    def close(self) -> None:
        error = None
        try:
            if self._controller_started:
                super().close()
        except _runtime_errors.RunnerError as exc:
            error = exc
        finally:
            try:
                if self._executor_started:
                    _runtime_utils._docker_checked(
                        "rm", "-f", self.executor_name, timeout=15
                    )
                    check = subprocess.run(
                        ["docker", "inspect", self.executor_name],
                        capture_output=True,
                        timeout=10,
                    )
                    if check.returncode == 0 or not any(
                        marker in check.stderr
                        for marker in (b"No such object:", b"No such container:")
                    ):
                        raise _runtime_errors.RunnerError(
                            "executor_termination_unverified"
                        )
            except _runtime_errors.RunnerError as exc:
                error = error or exc
        if error:
            raise error
