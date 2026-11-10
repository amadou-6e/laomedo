"""Separate OpenCode controller credentials from Docker command workers."""

from __future__ import annotations

import time
from pathlib import Path
from uuid import uuid4
import json
import secrets
import shutil
import threading

from laomedo.docker import DockerRuntime
from laomedo.container_images.errors import ImageBuildError
from laomedo.agents.agents.opencode.models import (
    OpenCodeConfig,
    OpenCodeRuntimeIdentity,
)
from laomedo.agents.agents.opencode.settings import CLI_VERSION
from laomedo.agents.agents.opencode.settings import CONTROLLER_LIFETIME_SECONDS
from laomedo.agents.agents.opencode.settings import WORKER_IMAGE
from laomedo.agents.agents.opencode.settings import WORKER_IMAGE_ID
from laomedo.agents.agents.opencode.utils import _credential_binding
from laomedo.agents.agents.opencode.utils import (
    check_auth_fresh as opencode_check_auth_fresh,
)
from laomedo.agents.agents.opencode.utils import model_metadata
from laomedo.agents.errors import RunnerError
from laomedo.agents.agents.base.utils import _json
from laomedo.agents.agents.base.utils import _private
from laomedo.agents.agents.base.utils import failure_observation


from laomedo.agents.agents.base.base import BaseInterruptibleCommandExecutor
from laomedo.agents.agents.base.models import (
    CommandRequest,
    CommandResult,
    CleanupObservation,
    CancellationObservation,
)
from laomedo.agents.agents.opencode.http.broker import OpenCodeCommandBroker


class OpenCodeCommandExecutor(BaseInterruptibleCommandExecutor):
    """Own credential-free worker execution and exact receipt cleanup, composed with an MCP adapter."""

    def __init__(
        self,
        workspace,
        canonical,
        store,
        evidence,
        *,
        worker_image_id=None,
        docker_endpoint=None,
        receipt_directory=None,
    ):
        """Bind admitted configuration and owned state; provider startup errors propagate before use."""
        self.workspace, self.canonical, self.store = workspace, canonical, store
        self.evidence = evidence
        self.closed = self.cleanup_failed = False
        self.error_code = None
        self.stopping = threading.Event()
        self.worker_image_id = worker_image_id or WORKER_IMAGE_ID
        self.docker_endpoint = docker_endpoint
        if self.worker_image_id is None:
            from py_docker.errors import DockerOperationError

            try:
                with DockerRuntime(
                    environment={"DOCKER_HOST": self.docker_endpoint}
                ).client() as client:
                    self.worker_image_id = DockerRuntime.ensure_image(
                        client, WORKER_IMAGE
                    )
            except ImageBuildError:
                raise RunnerError("container_image_build_failed") from None
            except DockerOperationError:
                raise RunnerError("opencode_workspace_command_failed") from None
        self.receipts = (
            Path(receipt_directory)
            if receipt_directory is not None
            else evidence.joinpath("docker-receipts")
        )
        self.receipts.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.allocated_receipts = set()
        self.drained = False
        self.capacity = threading.BoundedSemaphore(1)

        self.broker = OpenCodeCommandBroker(self)

    def request_cancel(self) -> CancellationObservation:
        """Reject admission and signal exact-job cancellation without waiting for drain."""
        with self.lock:
            self.closed = True
            self.stopping.set()
            idle = self.capacity.acquire(blocking=False)
            if idle:
                self.capacity.release()
        return CancellationObservation(requested=not idle, confirmed=None)

    def shutdown(self) -> CleanupObservation:
        """Stop admission, close owned resources and return exact cleanup evidence."""
        self.request_cancel()
        self.broker.server.shutdown()
        self.broker.server.server_close()
        self.broker.thread.join(timeout=5)
        acquired = self.capacity.acquire(timeout=180)
        if acquired:
            self.capacity.release()
        self.drained = acquired and not self.broker.thread.is_alive()
        if not acquired or self.cleanup_failed or self.broker.thread.is_alive():
            raise RunnerError("opencode_container_cleanup_unverified")
        return CleanupObservation(confirmed=True, scope="command_workers_and_broker")

    def execute(self, request: CommandRequest) -> CommandResult:
        """Execute an admitted command with typed output and confirmed worker cleanup."""
        if request.deadline is not None and request.deadline <= time.monotonic():
            return CommandResult(
                exit_code=124,
                stderr="worker_timeout",
                cleanup=CleanupObservation(confirmed=True, scope="no_worker_started"),
            )
        if (
            request.command is None
            or request.argv is not None
            or not request.command.strip()
            or len(request.command) > 16000
        ):
            raise RunnerError("invalid_worker_command")
        value = self._execute_native(request.command, deadline=request.deadline)
        return CommandResult(
            **value, cleanup=CleanupObservation(confirmed=True, scope="command_worker")
        )

    def _execute_native(self, command, *, deadline=None):
        """Run one credential-free worker; a receipt owns all cleanup uncertainty."""
        if not self.capacity.acquire(blocking=False):
            return {"exit_code": 75, "stdout": "", "stderr": "worker_busy"}
        try:
            with self.lock:
                if self.closed:
                    raise RunnerError("opencode_command_service_closed")
            from py_docker.containers.models import ContainerSpec, Mount
            from py_docker.jobs.models import ContainerJob
            from py_docker.streams.models import StreamLimits
            from py_docker.errors import (
                JobCancelledError,
                CleanupUnconfirmedError,
                DeadlineError,
                DockerOperationError,
                OutputLimitError,
            )

            name = "laomedo-oc-worker-" + uuid4().hex
            receipt_path = self.receipts.joinpath(name + ".json")
            with self.lock:
                self.allocated_receipts.add(receipt_path)
            try:
                result = DockerRuntime(
                    environment={"DOCKER_HOST": self.docker_endpoint}
                ).run_job(
                    ContainerJob(
                        spec=ContainerSpec(
                            image=self.worker_image_id,
                            name=name,
                            entrypoint=["timeout"],
                            command=[
                                "--signal=TERM",
                                "--kill-after=5s",
                                "60",
                                "sh",
                                "-c",
                                command,
                            ],
                            user="10001:10001",
                            network_mode="none",
                            read_only=False,
                            working_dir="/draft",
                            mounts=[
                                Mount(
                                    type="bind",
                                    source=str(source),
                                    target=target,
                                    read_only=readonly,
                                )
                                for source, target, readonly in (
                                    (self.workspace, "/draft", False),
                                    (self.canonical, "/canonical", True),
                                    (self.store, "/store", True),
                                )
                            ],
                        ),
                        limits=StreamLimits(seconds=70, max_bytes=1024 * 1024),
                        wait_timeout_seconds=10.0,
                        receipt_path=receipt_path,
                    ),
                    cancelled=self.stopping,
                    **({"deadline": deadline} if deadline is not None else {}),
                )
                value = {
                    "exit_code": result.exit_code,
                    "stdout": result.stdout.decode("utf-8", errors="replace")[:32768],
                    "stderr": result.stderr.decode("utf-8", errors="replace")[:32768],
                }
            except CleanupUnconfirmedError as error:
                self.cleanup_failed = True
                raise RunnerError(
                    "opencode_container_cleanup_unverified",
                    observation=failure_observation(
                        error,
                        stage="cleanup",
                        code="opencode_container_cleanup_unverified",
                    ),
                ) from None
            except JobCancelledError:
                value = {"exit_code": 130, "stdout": "", "stderr": "worker_cancelled"}
            except DeadlineError:
                value = {"exit_code": 124, "stdout": "", "stderr": "worker_timeout"}
            except OutputLimitError:
                self.error_code = "workspace_command_output_too_large"
                value = {
                    "exit_code": 125,
                    "stdout": "",
                    "stderr": "workspace_command_output_too_large",
                }
            except DockerOperationError:
                self.error_code = "opencode_workspace_command_failed"
                raise RunnerError("opencode_workspace_command_failed") from None
            with self.evidence.joinpath("worker-events.jsonl").open(
                "a", encoding="utf-8"
            ) as log:
                log.write(json.dumps({"command": command, **value}) + "\n")
            return value
        finally:
            self.capacity.release()
