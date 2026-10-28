"""Normal Codex native protocol over an owned py-docker interactive session."""

import json
import queue
import threading
from pathlib import Path

from laomedo.agents.providers.codex import settings
from laomedo.agents.providers.codex.native.base import BaseNativeServer
from laomedo.agents.providers.codex.native.models import CodexLaunch
from laomedo.agents.providers.codex.native.settings import Settings as TransportSettings
from laomedo.agents.runtime.errors import RunnerError


class AppServer(BaseNativeServer):
    """Keep application protocol state while py-docker owns container operations.

    Parameters
    ----------
    launch : CodexLaunch
        Canonical application image, mount and lease policy.
    evidence : Path
        Private per-run directory for activity and the durable container receipt.
    env : dict or None
        Preflight-selected host environment snapshot.
    secret_redactions : tuple[str, ...]
        Private application values removed from native output before recording.
    lifetime_seconds : float
        Explicit transport lifetime covering startup and allowed application turns.
    """

    def __init__(
        self,
        launch: CodexLaunch,
        evidence: Path,
        *,
        env=None,
        secret_redactions=(),
        lifetime_seconds: float = 60,
    ):
        """Create one SDK session with no Docker CLI or subprocess fallback."""
        self.telemetry = None
        self._client = None
        self.session = None
        self._reader_done = threading.Event()
        self._reader_failed = False
        self._closed = False
        self.cleanup_confirmed = False
        self._resource_lock = threading.Lock()
        self._resources_closed = False
        self._resources_failed = False
        self.events = []
        self.messages = queue.Queue()
        self.container_name = launch.name
        self.run_id = launch.run_id
        self.launch_token = (
            launch.launch_token.get_secret_value() if launch.launch_token else None
        )
        self.active_thread_id = None
        self.interrupt_acknowledged = False
        self.native_completion_status = None
        self.seq = 0
        self.secret_redactions = tuple(value for value in secret_redactions if value)
        self.log = evidence.joinpath("raw-events.jsonl").open("a", encoding="utf-8")
        self.activity_log = evidence.joinpath("activity-events.jsonl").open(
            "a", encoding="utf-8"
        )
        self.stderr = evidence.joinpath("stderr.log").open("a", encoding="utf-8")
        try:
            from py_docker import Client
            from py_docker.connection.settings import ConnectionSettings
            from py_docker.sessions.models import ContainerSession
            from py_docker.streams.models import StreamLimits

            spec = launch.to_container_spec()
            command = list(spec.command)
            if settings.Settings().multi_agent == "1":
                index = command.index("app-server")
                command[index:index] = [
                    "--disable",
                    "memories",
                    "-c",
                    "features.multi_agent=true",
                    "-c",
                    "agents.max_threads=2",
                    "-c",
                    "agents.max_depth=1",
                ]
            from laomedo.activity.runner.settings import Settings as ActivitySettings

            if ActivitySettings().otel == "1":
                from laomedo.activity.runner.telemetry import LaunchTelemetry

                self.telemetry = LaunchTelemetry(evidence)
                index = command.index("app-server")
                command[index:index] = self.telemetry.arguments()
                self.secret_redactions += (self.telemetry.token,)
            spec = spec.model_copy(update={"command": command})
            self._client = Client(
                settings=ConnectionSettings(timeout_seconds=15), environment=env
            )
            self.session = self._client.sessions.open(
                ContainerSession(
                    spec=spec,
                    limits=StreamLimits(
                        seconds=lifetime_seconds,
                        max_bytes=TransportSettings.load().max_bytes,
                    ),
                    receipt_path=evidence.joinpath(settings.NATIVE_RECEIPT_FILENAME),
                )
            )
            self.reader = threading.Thread(target=self._read_frames, daemon=True)
            self.reader.start()
        except Exception as primary_failure:
            failure = primary_failure
            if self.session is not None:
                from py_docker.errors import DockerOperationError

                try:
                    self.session.close()
                except DockerOperationError as cleanup:
                    failure = cleanup
            self._close_resources()
            if isinstance(failure, RunnerError):
                raise
            if isinstance(failure, ImportError):
                raise RunnerError("runner_transport_failed") from None
            from py_docker.errors import CleanupUnconfirmedError

            raise RunnerError(
                "container_termination_unverified"
                if isinstance(failure, CleanupUnconfirmedError)
                else "runner_transport_failed"
            ) from None

    @property
    def streams_closed(self) -> bool:
        """Report completion of the real multiplexed reader, without fake aliases."""
        return not self.reader.is_alive()

    def close(self) -> None:
        """Confirm exact removal before closing native evidence and the SDK client.

        Raises
        ------
        RunnerError
            Removal or reader shutdown cannot be confirmed.
        """
        from py_docker.errors import DockerOperationError

        if self._closed:
            return
        error = None
        try:
            self.session.close()
            self.cleanup_confirmed = True
        except (DockerOperationError, OSError):
            error = RunnerError("container_termination_unverified")
        finally:
            self._closed = True
            self.reader.join(timeout=5)
            if self.reader.is_alive():
                error = error or RunnerError("runner_transport_failed")
            else:
                self._close_resources()
                if self._resources_failed:
                    error = error or RunnerError("runner_transport_failed")
        if error is not None:
            raise error

    def _write(self, data: str) -> None:
        """Encode a complete JSON-RPC request and send it through bounded stdin."""
        from py_docker.errors import DockerOperationError

        try:
            self.session.write(data.encode("utf-8"))
        except (DockerOperationError, OSError, UnicodeError):
            raise RunnerError("runner_transport_failed") from None

    def _transport_exited(self) -> bool:
        """Use reader completion as the fast signal, then confirm exact state."""
        from py_docker.errors import DockerOperationError

        if not self._reader_done.is_set():
            return False
        try:
            if self._reader_failed:
                raise RunnerError("runner_transport_failed")
            return self.session.exited()
        except (DockerOperationError, OSError):
            raise RunnerError("runner_transport_failed") from None

    def _read_frames(self) -> None:
        """Decode and record complete native lines supplied by the owned session."""
        from py_docker.errors import DockerOperationError

        try:
            while (line := self.session.read_line()) is not None:
                self._record_line(line.channel, line.data.decode("utf-8"))
        except (
            DockerOperationError,
            OSError,
            UnicodeError,
            ValueError,
            TypeError,
            AttributeError,
            KeyError,
        ):
            self._reader_failed = True
        finally:
            self._reader_done.set()
            if self._closed:
                self._close_resources()

    def _record_line(self, channel: str, line: str) -> None:
        """Redact complete native lines before writing logs or activity events."""
        line = self._redact(line)
        if channel == "stderr":
            self.stderr.write(line)
            self.stderr.flush()
            return
        self.log.write(line)
        self.log.flush()
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            self.events.append({"method": "invalid/json"})
            return
        from laomedo.activity.runner import feed

        if feed.notification(event):
            self.activity_log.write(
                json.dumps(feed.receipt(event), ensure_ascii=False) + "\n"
            )
            self.activity_log.flush()
        self.messages.put(event)

    def _close_resources(self) -> None:
        """Close local evidence, telemetry and the owned client after transport use."""
        with self._resource_lock:
            if self._resources_closed:
                return
            self._resources_closed = True
            for resource in (
                self.log,
                self.activity_log,
                self.stderr,
                self.telemetry,
                self._client,
            ):
                if resource is None:
                    continue
                try:
                    resource.close()
                except (OSError, RuntimeError, ValueError):
                    self._resources_failed = True
