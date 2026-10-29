"""Credential-free Codex executor resource; ACP owns all agent communication."""

import hashlib
import re
import secrets
import threading
from pathlib import Path
from uuid import uuid4

from laomedo.agents.providers.codex import settings as _codex_settings
from laomedo.agents.runtime import errors as _runtime_errors


class Executor:
    """Own one exact-ID executor, its readiness checks and bounded stream drain."""

    def __init__(
        self, launch, evidence: Path, *, environment, lifetime_seconds, receipt_path
    ):
        from py_docker import Client
        from py_docker.containers.models import ContainerSpec, Mount
        from py_docker.sessions.models import ContainerSession
        from py_docker.streams.models import StreamLimits
        from laomedo.agents.providers.codex.controller.settings import Settings

        self.environment_id = "laomedo-executor-" + uuid4().hex
        self.token = secrets.token_hex(32)
        self.image = launch.image
        self.session = None
        self.reader = None
        self.read_failed = False
        self.client = Client(environment=environment)
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
            self.session = self.client.sessions.open(
                ContainerSession(
                    spec=spec,
                    limits=StreamLimits(
                        seconds=lifetime_seconds, max_bytes=Settings.load().max_bytes
                    ),
                    receipt_path=receipt_path.with_name(
                        receipt_path.stem + "-executor.json"
                    )
                    if receipt_path
                    else evidence / "executor-receipt.json",
                )
            )
            self.reader = threading.Thread(target=self._drain, daemon=True)
            self.reader.start()
        except Exception:
            self.close()
            raise

    def check_health(self):
        """Do not infer executor survival from the controller's ACP response."""
        try:
            if self.read_failed or not self.session.state().running:
                raise _runtime_errors.RunnerError("executor_lost")
        except RuntimeError:
            raise _runtime_errors.RunnerError("executor_lost") from None

    def _exec(self, identity, command):
        """Execute a bounded policy probe through the selected owned session."""
        from py_docker.errors import DockerOperationError
        from py_docker.streams.models import StreamLimits

        try:
            result = self.client.execution.run(
                identity, command, StreamLimits(seconds=5, max_bytes=65536)
            )
            if result.exit_code:
                raise _runtime_errors.RunnerError("docker_control_failed")
            return result.stdout.decode("utf-8").strip()
        except (DockerOperationError, UnicodeError):
            raise _runtime_errors.RunnerError("docker_control_unavailable") from None

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

    def exec_probe(self, command: list[str]):
        """Run a bounded readiness probe only inside the credential-free executor."""
        from py_docker.streams.models import StreamLimits

        return self.client.execution.run(
            self.session.identity, command, StreamLimits(seconds=15, max_bytes=65536)
        )

    def assert_controller_isolated(self, controller) -> None:
        if self._controller_listeners(controller):
            raise _runtime_errors.RunnerError("controller_listener_gate_failed")
        if (
            self._exec(controller.identity, ["codex", "--version"])
            != _codex_settings.CLI_VERSION
        ):
            raise _runtime_errors.RunnerError("unsupported_codex_cli_version")
        if self.read_failed or not self.session.state().running:
            raise _runtime_errors.RunnerError("executor_not_running")
        for session in (controller, self.session):
            container = self.client.containers.inspect(session.identity)
            if container is None or container.attrs["Image"] != self.image:
                raise _runtime_errors.RunnerError("running_image_digest_changed")

    def _drain(self) -> None:
        """Consume binary output under the session budget without retaining secrets."""
        from py_docker.errors import DockerOperationError

        try:
            while self.session.read_frame() is not None:
                pass
        except (DockerOperationError, OSError):
            self.read_failed = True

    def close(self) -> None:
        """Keep an unresolved executor receipt and report cleanup uncertainty."""
        from py_docker.errors import DockerOperationError

        try:
            if self.session is not None:
                self.session.close()
            if self.reader is not None and self.reader.ident is not None:
                self.reader.join(timeout=5)
                if self.reader.is_alive():
                    raise DockerOperationError("confirm executor reader shutdown")
        except DockerOperationError:
            raise _runtime_errors.RunnerError(
                "executor_termination_unverified"
            ) from None
        finally:
            self.client.close()
