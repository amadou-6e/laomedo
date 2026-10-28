"""Claude launch policy and credential-free workspace command mediation."""

from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import json
import math
import re
import secrets
import threading
import time

from laomedo.agents.providers.claude import settings as _claude_settings
from laomedo.agents.runtime import errors as _runtime_errors
from laomedo.host.leases import client as _leases_client
from laomedo.host.leases import settings as _leases_settings
from laomedo.host.leases import models as _leases_models
from laomedo.host.leases import utils as _leases_utils


class ClaudeContainer:
    """Keep provider policy here; delegate Docker lifecycle and receipts to py-docker."""

    def __init__(
        self,
        image=_claude_settings.IMAGE,
        profile=_claude_settings.PROFILE,
        lease_service=None,
    ):
        """Verify the local image, supervised cleanup and dedicated profile before use."""
        if (
            not isinstance(image, str)
            or not re.fullmatch(r"[A-Za-z0-9_./:@-]+", image)
            or not isinstance(profile, str)
            or not re.fullmatch(r"laomedo-claude-[a-z0-9-]+", profile)
        ):
            raise _runtime_errors.RunnerError("claude_container_configuration_invalid")
        self.profile, self.lease_service = profile, lease_service
        self.check_supervisor()
        try:
            from py_docker import Client
            from py_docker.errors import (
                CleanupUnconfirmedError,
                ConnectionConfigurationError,
                DockerOperationError,
            )
        except ImportError:
            raise _runtime_errors.RunnerError("claude_container_unavailable") from None
        try:
            with Client() as docker:
                self.docker_endpoint = docker.connection.endpoint
                try:
                    self.image_id = docker.images.resolve(image)
                except DockerOperationError:
                    raise _runtime_errors.RunnerError(
                        "claude_container_image_missing"
                    ) from None
                self.receipts = Path(lease_service).parent.joinpath("receipts")
                self.receipts.mkdir(mode=0o700, parents=True, exist_ok=True)
                for receipt in self.receipts.glob("claude-*.json"):
                    docker.sessions.recover(receipt)
                labels = {"laomedo.provider": "claude"}
                if not docker.volumes.exists(profile):
                    docker.volumes.create(name=profile, labels=labels)
                if not docker.volumes.has_labels(profile, labels):
                    raise _runtime_errors.RunnerError(
                        "claude_container_profile_unavailable"
                    )
        except CleanupUnconfirmedError:
            raise _runtime_errors.RunnerError("container_termination_unverified") from None
        except ConnectionConfigurationError:
            raise _runtime_errors.RunnerError(
                "claude_container_configuration_invalid"
            ) from None
        except DockerOperationError:
            raise _runtime_errors.RunnerError("claude_container_unavailable") from None
        version = self.control(["--version"], timeout=60)
        if (
            version.exit_code
            or version.stdout.decode().strip()
            != _claude_settings.CLI_VERSION + " (Claude Code)"
        ):
            raise _runtime_errors.RunnerError("unsupported_claude_cli_version")

    @contextmanager
    def client(self, *, output_code="workspace_command_output_too_large"):
        """Pin the daemon and translate library failures at the provider boundary."""
        from py_docker import Client
        from py_docker.errors import (
            CleanupUnconfirmedError,
            DeadlineError,
            DockerOperationError,
            OutputLimitError,
        )

        try:
            with Client(environment={"DOCKER_HOST": self.docker_endpoint}) as docker:
                yield docker
        except CleanupUnconfirmedError:
            raise _runtime_errors.RunnerError(
                "container_termination_unverified"
            ) from None
        except OutputLimitError:
            raise _runtime_errors.RunnerError(output_code) from None
        except DeadlineError:
            raise _runtime_errors.RunnerError("claude_turn_timeout") from None
        except DockerOperationError:
            raise _runtime_errors.RunnerError("claude_container_unavailable") from None

    def spec(
        self,
        command,
        *,
        name=None,
        run_id=None,
        token=None,
        workspace=None,
        worker=False,
        environment=None,
        mounts=(),
        extra_hosts=None,
    ):
        """Build the canonical sandbox policy for a controller or isolated worker."""
        from py_docker.containers.models import ContainerSpec, Mount

        selected = list(mounts)
        env = dict(environment or {})
        if worker:
            env.update(HOME="/tmp", CLAUDE_CONFIG_DIR="/tmp/unused")
        else:
            selected.append(
                Mount(type="volume", source=self.profile, target="/profile")
            )
        if workspace is not None:
            skills = str(workspace.joinpath(".agents/skills"))
            selected.extend(
                [
                    Mount(type="bind", source=str(workspace), target="/draft"),
                    Mount(
                        type="bind",
                        source=skills,
                        target="/draft/.agents/skills",
                        read_only=True,
                    ),
                    Mount(
                        type="bind",
                        source=skills,
                        target="/draft/.claude/skills",
                        read_only=True,
                    ),
                ]
            )
        return ContainerSpec(
            image=self.image_id,
            name=name or "laomedo-claude-control-" + uuid4().hex,
            entrypoint=command[:1],
            command=command[1:],
            init=True,
            nano_cpus=2_000_000_000,
            working_dir="/draft",
            network_mode="none" if worker else "bridge",
            tmpfs={"/tmp": "rw,nosuid,nodev,size=256m"},
            mounts=selected,
            environment=env,
            extra_hosts=extra_hosts or {},
            labels={
                _leases_settings.LABEL_RUN: run_id,
                _leases_settings.LABEL_TOKEN: token,
            }
            if run_id
            else {},
        )

    def guarded(self, command, deadline):
        """Bound the process tree inside the container even if its host disappears."""
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _runtime_errors.RunnerError("claude_turn_timeout")
        return [
            "python3",
            "-c",
            _claude_settings.EXECUTION_GUARD,
            str(time.time() + remaining),
            str(remaining),
            *command,
        ]

    def job(self, spec, *, timeout):
        """Collect one bounded binary result only after exact cleanup is confirmed."""
        from py_docker.jobs.models import ContainerJob
        from py_docker.streams.models import StreamLimits

        with self.client() as docker:
            return docker.jobs.run(
                ContainerJob(
                    spec=spec,
                    limits=StreamLimits(
                        seconds=timeout + 10, max_bytes=36 * 1024 * 1024
                    ),
                    receipt_path=self.receipts.joinpath(
                        "claude-" + spec.name + ".json"
                    ),
                    wait_timeout_seconds=10.0,
                )
            )

    @contextmanager
    def session(self, spec, receipt, seconds):
        """Keep output and durable cleanup on the launcher's creator thread."""
        from py_docker.sessions.models import ContainerSession
        from py_docker.streams.models import StreamLimits

        with self.client(output_code="claude_receipt_too_large") as docker:
            with docker.sessions.open(
                ContainerSession(
                    spec=spec,
                    receipt_path=receipt,
                    limits=StreamLimits(seconds=seconds, max_bytes=36 * 1024 * 1024),
                )
            ) as session:
                yield session

    def control(self, args, *, input=None, timeout=45):
        """Run a zero-turn CLI request; input files avoid Windows pipe half-close."""
        from py_docker.containers.models import Mount

        with TemporaryDirectory(prefix="claude-input-", dir=self.receipts) as directory:
            mounts = []
            command = ["claude", *args]
            if input is not None:
                source = Path(directory).joinpath("input")
                source.write_bytes(input)
                source.chmod(0o600)
                mounts = [
                    Mount(
                        type="bind",
                        source=str(source),
                        target="/run/laomedo/input",
                        read_only=True,
                    )
                ]
                command = ["sh", "-c", 'exec "$@" < /run/laomedo/input', "sh", *command]
            spec = self.spec(
                self.guarded(command, time.monotonic() + timeout), mounts=mounts
            )
            return self.job(spec, timeout=timeout)

    def check_supervisor(self):
        """Never advertise a runnable API without independent cleanup supervision."""
        from pathlib import Path

        if self.lease_service is None:
            raise _runtime_errors.RunnerError("lease_service_required")
        try:
            root = Path(self.lease_service)
            info = json.loads((root / "service.json").read_text())
            wall = float((root / "service.alive").read_text())
            monotonic = float((root / "service.alive.monotonic").read_text())
            if (
                not isinstance(info.get("pid"), int)
                or not info.get("instance")
                or not math.isfinite(wall)
                or not math.isfinite(monotonic)
                or not -1
                <= time.time() - wall
                <= _leases_settings.SERVICE_STALE_SECONDS
                or not -1
                <= time.monotonic() - monotonic
                <= _leases_settings.SERVICE_STALE_SECONDS
            ):
                raise ValueError()
        except (OSError, ValueError, TypeError, AttributeError):
            raise _runtime_errors.RunnerError("lease_service_unavailable") from None

    def lease(self, run_id, name, token, cancelled, scope=None):
        if self.lease_service is None:
            raise _runtime_errors.RunnerError("lease_service_required")
        try:
            return _leases_client.LeaseClient(
                self.lease_service,
                run_id=run_id,
                docker_endpoint=self.docker_endpoint,
                name=name,
                token=token,
                cancelled=cancelled,
                mediation_request=scope,
            )
        except (OSError, RuntimeError):
            raise _runtime_errors.RunnerError("lease_service_unavailable") from None


class CommandService:
    """One run capability; all commands execute without the Claude profile/network."""

    def __init__(self, runtime, root, record, cancelled, deadline, *, mediation=None):
        self.runtime, self.root, self.record = runtime, root, record
        self.cancelled, self.deadline = cancelled, deadline
        self.mediation = mediation
        self.token = secrets.token_hex(32)
        self.lock = threading.Lock()
        self.cleanup_failed = False
        self.error_code = None
        self.active_lock = threading.Lock()
        self.active = {}
        self.closed = False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                if self.path != "/command" or not secrets.compare_digest(
                    self.headers.get("Authorization", ""), "Bearer " + owner.token
                ):
                    self.send_error(403)
                    return
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 65536:
                        raise ValueError()
                    value = json.loads(self.rfile.read(size))
                    answer = (
                        owner.mediate(value["github"])
                        if isinstance(value, dict) and set(value) == {"github"}
                        else owner.execute(value)
                    )
                    raw = json.dumps(answer).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                except Exception:
                    self.send_error(503, "Workspace command unavailable")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.secret_path = root / ("command-capability-" + uuid4().hex)
        self.secret_path.write_text(self.token, encoding="ascii")
        self.url = f"http://host.docker.internal:{self.server.server_port}/command"

    def execute(self, value):
        if (
            not isinstance(value, dict)
            or set(value) != {"command"}
            or not isinstance(value["command"], str)
        ):
            raise _runtime_errors.RunnerError("claude_workspace_command_invalid")
        if not value["command"].strip() or len(value["command"]) > 60000:
            raise _runtime_errors.RunnerError("claude_workspace_command_invalid")
        with self.lock:
            if (
                self.closed
                or self.cancelled.is_set()
                or time.monotonic() >= self.deadline
            ):
                raise _runtime_errors.RunnerError("claude_cancelled")
            name, token = "laomedo-claude-command-" + uuid4().hex, uuid4().hex
            lease = self.runtime.lease(
                self.record["run_id"], name, token, self.cancelled
            )
            with self.active_lock:
                self.active[name] = token
            cleanup_confirmed = job_started = False
            try:
                worker_deadline = min(self.deadline, time.monotonic() + 120)
                spec = self.runtime.spec(
                    self.runtime.guarded(
                        ["sh", "-c", value["command"]], worker_deadline
                    ),
                    name=name,
                    run_id=self.record["run_id"],
                    token=token,
                    workspace=self.root.joinpath("workspace"),
                    worker=True,
                )
                job_started = True
                result = self.runtime.job(
                    spec, timeout=max(1, worker_deadline - time.monotonic())
                )
                cleanup_confirmed = True
                return {
                    "exit_code": result.exit_code,
                    "output": (result.stdout + result.stderr)[: 1024 * 1024].decode(
                        "utf-8", errors="replace"
                    ),
                }
            except _runtime_errors.RunnerError as error:
                if str(error) == "workspace_command_output_too_large":
                    self.error_code = "workspace_command_output_too_large"
                cleanup_confirmed = (
                    job_started and str(error) != "container_termination_unverified"
                )
                raise
            finally:
                verified = cleanup_confirmed
                if not verified:
                    verified, _ = _leases_utils.cleanup_exact(
                        _leases_models.ContainerIdentity(
                            name=name,
                            run_id=self.record["run_id"],
                            token=token,
                            docker_endpoint=self.runtime.docker_endpoint,
                        )
                    )
                if verified:
                    try:
                        lease.finish()
                    except RuntimeError:
                        verified = False
                else:
                    lease.stop_heartbeats()
                with self.active_lock:
                    self.active.pop(name, None)
                if not verified:
                    self.cleanup_failed = True
                    self.cancelled.set()
                    raise _runtime_errors.RunnerError(
                        "container_termination_unverified"
                    )

    def mediate(self, value):
        from urllib.request import Request
        from urllib.request import urlopen
        from urllib.error import HTTPError

        if self.mediation is None or self.closed or self.cancelled.is_set():
            raise _runtime_errors.RunnerError("mediated_grant_unavailable")
        if (
            not isinstance(value, dict)
            or set(value) - {"operation", "payload", "effect_id"}
            or not isinstance(value.get("operation"), str)
            or not isinstance(value.get("payload"), dict)
        ):
            raise _runtime_errors.RunnerError("claude_workspace_command_invalid")
        url, instance, secret_path = self.mediation
        body = {**value, "repository": self.record["github_scope"]["repository"]}
        request = Request(
            url.replace("host.docker.internal", "127.0.0.1"),
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + secret_path.read_text().strip(),
                "X-Laomedo-Mediator-Instance": instance,
            },
        )
        try:
            with urlopen(request, timeout=20) as response:
                return json.load(response)
        except HTTPError:
            # A known refusal is terminal for this request and contains no raw response.
            return {"error": "mediation_request_refused"}
        except Exception:
            self.record["mediation_outcome"] = "unknown"
            self.cancelled.set()
            raise _runtime_errors.RunnerError(
                "claude_mediation_outcome_unknown"
            ) from None

    def close(self):
        self.closed = True
        with self.active_lock:
            active = list(self.active.items())
        for name, token in active:
            verified, _ = _leases_utils.cleanup_exact(
                _leases_models.ContainerIdentity(
                    name=name,
                    run_id=self.record["run_id"],
                    token=token,
                    docker_endpoint=self.runtime.docker_endpoint,
                )
            )
            if not verified:
                self.cleanup_failed = True
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        # Wait for any command's exact cleanup before freezing the workspace.
        with self.lock:
            self.secret_path.unlink(missing_ok=True)
        if self.cleanup_failed:
            raise _runtime_errors.RunnerError("container_termination_unverified")
