"""Own native app-server processes and the split-controller boundary."""

from __future__ import annotations

import hashlib
import os
import queue
import re
import secrets
import subprocess
import threading
import time
from pathlib import Path
from uuid import uuid4

import laomedo.agents.providers.codex.settings as _codex_settings
import laomedo.agents.providers.codex.utils as _codex_utils
import laomedo.agents.runtime.errors as _runtime_errors
from laomedo.agents.providers.codex.split.transport import SplitTransport


class SplitAppServer(SplitTransport):
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
        docker_environment=None,
    ):
        self.docker_environment = docker_environment
        self.executor_name = "laomedo-executor-" + uuid4().hex
        self.environment_id = "laomedo-executor-" + uuid4().hex
        self.executor_token = secrets.token_hex(32)
        self.registered = False
        self.authorization_probe = None
        self._controller_started = False
        self._executor_started = False
        if (
            self._docker_checked(
                "image", "inspect", _codex_settings.IMAGE, "--format", "{{.Id}}"
            )
            != _codex_settings.IMAGE_ID
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
            _codex_settings.IMAGE,
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
            self._docker_checked(*executor, timeout=30)
            self._executor_started = True
            command = _codex_utils._docker_prefix(
                workspace, canonical, store_mount, nested_sandbox=False
            )
            command[command.index("--network") + 1] = "container:" + self.executor_name
            old_mount = f"type=volume,source={_codex_settings.VOLUME},target=/home/runner/.codex"
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
            environment = docker_environment
            if access_token is not None:
                if not isinstance(access_token, str) or not access_token:
                    raise _runtime_errors.RunnerError("invalid_controller_token")
                command[command.index("--workdir") : command.index("--workdir")] = [
                    "--env",
                    "ACCESS_TOKEN",
                ]
                environment = dict(
                    os.environ if docker_environment is None else docker_environment,
                    ACCESS_TOKEN=access_token,
                )
            super().__init__(
                ["docker", *command],
                evidence,
                env=environment,
                docker_environment=docker_environment,
            )
            self._controller_started = True
        except Exception:
            if self._executor_started:
                subprocess.run(
                    ["docker", "rm", "-f", self.executor_name],
                    check=False,
                    env=self.docker_environment,
                    capture_output=True,
                    timeout=15,
                )
            raise

    def _docker_checked(self, *args: str, timeout: float = 15) -> str:
        """Run a split control operation on the preflight-selected Docker endpoint.

        Parameters
        ----------
        *args : str
            Docker CLI arguments supplied by the split controller.
        timeout : float
            Maximum seconds allowed for this control request.

        Returns
        -------
        str
            Stripped output; existing Docker control errors propagate unchanged.
        """
        return _codex_utils._docker_checked(
            *args, timeout=timeout, env=self.docker_environment
        )

    def _controller_listeners(self) -> set[str]:
        """Reject controller-owned listening TCP/Unix and any UDP socket."""
        fds = self._docker_checked(
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
            rows = self._docker_checked(
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
        rows = self._docker_checked(
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
            self._docker_checked(
                "exec", self.container_name, "codex", "--version", timeout=5
            )
            != _codex_settings.CLI_VERSION
        ):
            raise _runtime_errors.RunnerError("unsupported_codex_cli_version")
        if (
            self._docker_checked(
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
                self._docker_checked(
                    "inspect", name, "--format", "{{.Image}}", timeout=5
                )
                != _codex_settings.IMAGE_ID
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
                    self._docker_checked(
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
                    self._docker_checked("rm", "-f", self.executor_name, timeout=15)
                    check = subprocess.run(
                        ["docker", "inspect", self.executor_name],
                        check=False,
                        env=self.docker_environment,
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
