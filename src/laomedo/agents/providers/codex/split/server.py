"""Own native app-server processes and the split-controller boundary."""

from __future__ import annotations

import hashlib
import queue
import re
import secrets
import threading
import time
from pathlib import Path
from uuid import uuid4

import laomedo.agents.providers.codex.settings as _codex_settings
import laomedo.agents.runtime.errors as _runtime_errors
from laomedo.agents.providers.codex.native.server import AppServer


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
        docker_environment=None,
        lifetime_seconds: float = 300,
        receipt_path: Path | None = None,
    ):
        """Open both exact-ID sessions on the preflight-selected endpoint."""
        from py_docker import Client
        from py_docker.containers.models import ContainerSpec, Mount
        from py_docker.sessions.models import ContainerSession
        from py_docker.streams.models import StreamLimits

        from laomedo.agents.providers.codex.split.models import SplitLaunch

        if access_token is not None and (
            not isinstance(access_token, str) or not access_token
        ):
            raise _runtime_errors.RunnerError("invalid_controller_token")
        from laomedo.agents.providers.codex.native.settings import (
            Settings as TransportSettings,
        )

        self.docker_environment = docker_environment
        self.executor_name = "laomedo-executor-" + uuid4().hex
        self.environment_id = "laomedo-executor-" + uuid4().hex
        self.executor_token = secrets.token_hex(32)
        self.registered = False
        self.authorization_probe = None
        self._controller_started = False
        self.executor = None
        self._executor_reader = None
        self._executor_read_failed = False
        self._executor_client = Client(environment=docker_environment)
        try:
            image = self._executor_client.images.resolve(
                _codex_settings.IMAGE, expected_id=_codex_settings.IMAGE_ID
            )
            spec = ContainerSpec(
                image=image,
                name=self.executor_name,
                stdin_open=True,
                command=[
                    "codex",
                    "exec-server",
                    "--listen",
                    "ws://0.0.0.0:39871",
                    "--ws-auth",
                    "capability-token",
                    "--ws-token-sha256",
                    hashlib.sha256(self.executor_token.encode()).hexdigest(),
                ],
                user="10001:10001",
                network_mode="bridge",
                read_only=False,
                working_dir="/draft",
                mounts=[Mount(type="bind", source=str(workspace), target="/draft")],
                tmpfs={"/home/runner/.codex": "rw,uid=10001,gid=10001,mode=0700"},
            )
            self.executor = self._executor_client.sessions.open(
                ContainerSession(
                    spec=spec,
                    limits=StreamLimits(
                        seconds=lifetime_seconds,
                        max_bytes=TransportSettings.load().max_bytes,
                    ),
                    receipt_path=(
                        receipt_path.with_name(receipt_path.stem + "-executor.json")
                        if receipt_path is not None
                        else evidence.joinpath("executor-receipt.json")
                    ),
                )
            )
            self._executor_reader = threading.Thread(
                target=self._drain_executor, daemon=True
            )
            self._executor_reader.start()
            launch = SplitLaunch(
                workspace=workspace,
                canonical=canonical,
                store_mount=store_mount,
                image=image,
                profile=profile,
                executor_id=self.executor.identity.id,
                provider_config=tuple(provider_config),
                access_token=access_token,
            )
            super().__init__(
                launch,
                evidence,
                env=docker_environment,
                lifetime_seconds=lifetime_seconds,
                receipt_path=receipt_path,
                secret_redactions=((access_token,) if access_token else ()),
            )
            self._controller_started = True
        except Exception as primary:
            try:
                self._close_executor()
            except _runtime_errors.RunnerError as cleanup:
                raise cleanup from primary
            from py_docker.errors import (
                CleanupUnconfirmedError,
                DockerOperationError,
                OwnershipConflictError,
            )

            if isinstance(primary, CleanupUnconfirmedError):
                raise _runtime_errors.RunnerError(
                    "executor_termination_unverified"
                ) from None
            if isinstance(primary, OwnershipConflictError):
                raise _runtime_errors.RunnerError(
                    "docker_image_digest_changed"
                ) from None
            if isinstance(primary, DockerOperationError):
                raise _runtime_errors.RunnerError("docker_control_failed") from None
            raise

    def _exec(self, identity, command):
        """Execute a bounded policy probe through the selected owned session."""
        from py_docker.errors import DockerOperationError
        from py_docker.streams.models import StreamLimits

        try:
            result = self._executor_client.execution.run(
                identity, command, StreamLimits(seconds=5, max_bytes=65536)
            )
            if result.exit_code:
                raise _runtime_errors.RunnerError("docker_control_failed")
            return result.stdout.decode("utf-8").strip()
        except (DockerOperationError, UnicodeError):
            raise _runtime_errors.RunnerError("docker_control_unavailable") from None

    def _controller_listeners(self) -> set[str]:
        """Reject controller-owned listening TCP/Unix and any UDP socket."""
        fds = self._exec(
            self.session.identity, ["sh", "-c", "ls -l /proc/[0-9]*/fd 2>/dev/null"]
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
            rows = self._exec(self.session.identity, ["cat", "/proc/net/" + table])
            for row in rows.splitlines()[1:]:
                fields = row.split()
                if (
                    len(fields) > 9
                    and fields[9] in owned
                    and (kind == "udp" or fields[3] == "0A")
                ):
                    found.add(kind)
        rows = self._exec(self.session.identity, ["cat", "/proc/net/unix"])
        for row in rows.splitlines()[1:]:
            fields = row.split()
            if len(fields) > 6 and fields[6] in owned and int(fields[3], 16) & 0x10000:
                found.add("unix")
        return found

    def exec_probe(self, command: list[str]):
        """Run a bounded readiness probe only inside the credential-free executor."""
        from py_docker.streams.models import StreamLimits

        return self._executor_client.execution.run(
            self.executor.identity, command, StreamLimits(seconds=15, max_bytes=65536)
        )

    def assert_controller_isolated(self) -> None:
        if self._controller_listeners():
            raise _runtime_errors.RunnerError("controller_listener_gate_failed")
        if (
            self._exec(self.session.identity, ["codex", "--version"])
            != _codex_settings.CLI_VERSION
        ):
            raise _runtime_errors.RunnerError("unsupported_codex_cli_version")
        if self._executor_read_failed or not self.executor.state().running:
            raise _runtime_errors.RunnerError("executor_not_running")
        for session in (self.session, self.executor):
            container = self._executor_client.containers.inspect(session.identity)
            if (
                container is None
                or container.attrs["Image"] != _codex_settings.IMAGE_ID
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
                if self._executor_read_failed or not self.executor.state().running:
                    return "unknown", "executor_lost"
            except RuntimeError:
                return "unknown", "executor_lost"
            try:
                msg = self.messages.get(timeout=min(0.25, deadline - time.monotonic()))
            except queue.Empty:
                if self._transport_exited():
                    return "unknown", "controller_exited"
                continue
            self._observe(msg)
        self.interrupt(turn_id)
        return "timeout", "turn_timeout"

    def close(self) -> None:
        """Confirm controller and executor removal before releasing clients."""
        error = None
        try:
            if self._controller_started:
                super().close()
        except _runtime_errors.RunnerError as failure:
            error = failure
        try:
            self._close_executor()
        except _runtime_errors.RunnerError as failure:
            error = failure
        if error is not None:
            raise error

    def _drain_executor(self) -> None:
        """Consume binary output under the session budget without retaining secrets."""
        from py_docker.errors import DockerOperationError

        try:
            while self.executor.read_frame() is not None:
                pass
        except (DockerOperationError, OSError):
            self._executor_read_failed = True

    def _close_executor(self) -> None:
        """Keep an unresolved executor receipt and report cleanup uncertainty."""
        from py_docker.errors import DockerOperationError

        try:
            if self.executor is not None:
                self.executor.close()
            if (
                self._executor_reader is not None
                and self._executor_reader.ident is not None
            ):
                self._executor_reader.join(timeout=5)
                if self._executor_reader.is_alive():
                    raise DockerOperationError("confirm executor reader shutdown")
        except DockerOperationError:
            raise _runtime_errors.RunnerError(
                "executor_termination_unverified"
            ) from None
        finally:
            self._executor_client.close()
