"""Own native app-server processes and the split-controller boundary."""

from __future__ import annotations

import json
import queue
import subprocess
import threading
from pathlib import Path

import laomedo.activity.runner.settings as _runner_settings
import laomedo.agents.providers.codex.settings as _codex_settings
import laomedo.agents.runtime.errors as _runtime_errors
import laomedo.host.leases.models as _leases_models
import laomedo.host.leases.settings as _leases_settings
import laomedo.host.leases.utils as _leases_utils
from laomedo.agents.providers.codex.native.base import BaseNativeServer


class SplitTransport(BaseNativeServer):
    """Explicit CLI transport for split controllers and historical CLI probes."""

    def __init__(
        self,
        command: list[str],
        evidence: Path,
        *,
        env=None,
        secret_redactions=(),
        docker_environment=None,
    ):
        self.docker_environment = docker_environment
        self.telemetry = None
        if _runner_settings.Settings().otel == "1":
            import laomedo.activity.runner.telemetry as _runner_telemetry

            self.telemetry = _runner_telemetry.LaunchTelemetry(evidence)
            index = command.index("app-server")
            command = command[:index] + self.telemetry.arguments() + command[index:]
        if _codex_settings.Settings().multi_agent == "1":
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
                        check=False,
                        env=getattr(self, "docker_environment", None),
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
                        check=False,
                        env=getattr(self, "docker_environment", None),
                        capture_output=True,
                        timeout=15,
                    )
                    probe = subprocess.run(
                        ["docker", "inspect", self.container_name],
                        check=False,
                        env=getattr(self, "docker_environment", None),
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

    @property
    def streams_closed(self) -> bool:
        """Report actual reader completion for the split transport's two pipes."""
        return not self.reader.is_alive() and not self.stderr_reader.is_alive()

    def _write(self, data: str) -> None:
        """Write and flush one complete request to the split CLI stdin pipe."""
        self.process.stdin.write(data)
        self.process.stdin.flush()

    def _transport_exited(self) -> bool:
        """Check the split CLI process without changing its existing semantics."""
        return self.process.poll() is not None
