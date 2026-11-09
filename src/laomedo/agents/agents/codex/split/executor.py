"""Credential-free Codex executor resource; ACP owns all agent communication."""

from laomedo.agents.agents.base.runtime import AgentDockerMechanism
import hashlib
import re
import secrets
import threading
import time
from pathlib import Path
from uuid import uuid4

from laomedo.agents.agents.codex.settings import CLI_VERSION
from laomedo.agents.errors import RunnerError
from laomedo.agents.agents.base.base import BaseSplitCommandExecutor
from laomedo.agents.agents.base.models import (
    CommandRequest,
    CommandResult,
    CleanupObservation,
    ProcessHealthObservation,
    IsolationObservation,
)


class CodexCommandExecutor(BaseSplitCommandExecutor):
    """Own one exact-ID executor, its readiness checks and bounded stream drain."""

    def __init__(
        self, launch, evidence: Path, *, environment, lifetime_seconds, receipt_path
    ):
        """Bind admitted configuration and owned state; provider startup errors propagate before use."""
        from py_docker.containers.models import ContainerSpec, Mount
        from py_docker.sessions.models import ContainerSession
        from py_docker.streams.models import StreamLimits
        from laomedo.agents.agents.codex.controller.settings import Settings

        self.environment_id = "laomedo-executor-" + uuid4().hex
        self.token = secrets.token_hex(32)
        self.image = launch.image
        self.session = None
        self.reader = None
        self.read_failed = False
        self.client = AgentDockerMechanism(environment=environment).connect()
        try:
            spec = ContainerSpec(
                image=self.image,
                name=self.environment_id,
                stdin_open=True,
                command=[
                    "codex",
                    "exec-server",
                    "--listen",
                    "ws://0.0.0.0:39871",
                    "--ws-auth",
                    "capability-token",
                    "--ws-token-sha256",
                    hashlib.sha256(self.token.encode()).hexdigest(),
                ],
                user="10001:10001",
                network_mode="bridge",
                read_only=False,
                working_dir="/draft",
                mounts=[
                    Mount(type="bind", source=str(launch.workspace), target="/draft")
                ],
                tmpfs={"/home/runner/.codex": "rw,uid=10001,gid=10001,mode=0700"},
                security_opt=launch.to_container_spec().security_opt,
            )
            self.session = AgentDockerMechanism.start_session(
                self.client,
                ContainerSession(
                    spec=spec,
                    limits=StreamLimits(
                        seconds=lifetime_seconds, max_bytes=Settings.load().max_bytes
                    ),
                    receipt_path=(
                        receipt_path.with_name(receipt_path.stem + "-executor.json")
                        if receipt_path
                        else evidence / "executor-receipt.json"
                    ),
                ),
            )
            self.reader = threading.Thread(target=self._drain, daemon=True)
            self.reader.start()
        except Exception:
            self.shutdown()
            raise

    def check_health(self):
        """Do not infer executor survival from the controller's ACP response."""
        try:
            if self.read_failed or not self.session.state().running:
                raise RunnerError("executor_lost")
        except RuntimeError:
            raise RunnerError("executor_lost") from None
        return ProcessHealthObservation(
            alive=True, scope="codex_executor_session_and_reader"
        )

    def assert_controller_isolated(self, controller) -> IsolationObservation:
        """Verify the existing split-controller gates and image identities; a passed handshake alone is insufficient."""
        if self._controller_listeners(controller):
            raise RunnerError("controller_listener_gate_failed")
        if self._exec(controller.identity, ["codex", "--version"]) != CLI_VERSION:
            raise RunnerError("unsupported_codex_cli_version")
        if self.read_failed or not self.session.state().running:
            raise RunnerError("executor_not_running")
        for session in (controller, self.session):
            container = self.client.containers.inspect(session.identity)
            if container is None or container.attrs["Image"] != self.image:
                raise RunnerError("running_image_digest_changed")
        return IsolationObservation(
            verified=True, scope="codex_split_controller_and_executor"
        )

    def shutdown(self) -> CleanupObservation:
        """Stop admission, close owned resources and return exact cleanup evidence."""
        from py_docker.errors import DockerOperationError

        try:
            if self.session is not None:
                AgentDockerMechanism.close_session(self.session)
            if self.reader is not None and self.reader.ident is not None:
                self.reader.join(timeout=5)
                if self.reader.is_alive():
                    raise DockerOperationError("confirm executor reader shutdown")
        except DockerOperationError:
            raise RunnerError("executor_termination_unverified") from None
        finally:
            self.client.close()
        return CleanupObservation(confirmed=True, scope="codex_executor_and_reader")

    def execute(self, request: CommandRequest) -> CommandResult:
        """Execute once in the owned credential-free container; never retry timeout."""
        from py_docker.streams.models import StreamLimits

        seconds = 15.0
        if request.deadline is not None:
            seconds = min(seconds, request.deadline - time.monotonic())
            if seconds <= 0:
                return CommandResult(
                    exit_code=124,
                    stderr="worker_timeout",
                    cleanup=CleanupObservation(confirmed=True, scope="no_exec_started"),
                )
        result = AgentDockerMechanism.run_command(
            self.client,
            self.session.identity,
            request.argv if request.argv is not None else ["sh", "-c", request.command],
            StreamLimits(seconds=seconds, max_bytes=65536),
        )
        return CommandResult(
            exit_code=result.exit_code,
            stdout=result.stdout.decode("utf-8", errors="replace"),
            stderr=result.stderr.decode("utf-8", errors="replace"),
            cleanup=CleanupObservation(confirmed=True, scope="exec_process_only"),
        )

    def _exec(self, identity, command):
        """Execute a bounded policy probe through the selected owned session."""
        from py_docker.errors import DockerOperationError
        from py_docker.streams.models import StreamLimits

        try:
            result = AgentDockerMechanism.run_command(
                self.client, identity, command, StreamLimits(seconds=5, max_bytes=65536)
            )
            if result.exit_code:
                raise RunnerError("docker_control_failed")
            return result.stdout.decode("utf-8").strip()
        except (DockerOperationError, UnicodeError):
            raise RunnerError("docker_control_unavailable") from None

    def _controller_listeners(self, controller) -> set[str]:
        """Reject controller-owned listening TCP/Unix and any UDP socket."""
        fds = self._exec(
            controller.identity, ["sh", "-c", "ls -l /proc/[0-9]*/fd 2>/dev/null"]
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
            rows = self._exec(controller.identity, ["cat", "/proc/net/" + table])
            for row in rows.splitlines()[1:]:
                fields = row.split()
                if (
                    len(fields) > 9
                    and fields[9] in owned
                    and (kind == "udp" or fields[3] == "0A")
                ):
                    found.add(kind)
        rows = self._exec(controller.identity, ["cat", "/proc/net/unix"])
        for row in rows.splitlines()[1:]:
            fields = row.split()
            if len(fields) > 6 and fields[6] in owned and int(fields[3], 16) & 0x10000:
                found.add("unix")
        return found

    def _drain(self) -> None:
        """Consume binary output under the session budget without retaining secrets."""
        from py_docker.errors import DockerOperationError

        try:
            while self.session.read_frame() is not None:
                pass
        except (DockerOperationError, OSError):
            self.read_failed = True
