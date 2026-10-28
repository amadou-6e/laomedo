"""Claude controller containers and credential-free, network-free command workers."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from uuid import uuid4
import json
import laomedo.agents.providers.claude.constants as _claude_constants
import laomedo.agents.providers.claude.utils as _claude_utils
import laomedo.agents.runtime.errors as _runtime_errors
import laomedo.host.leases.client as _leases_client
import laomedo.host.leases.constants as _leases_constants
import laomedo.host.leases.models as _leases_models
import laomedo.host.leases.utils as _leases_utils
import math
import re
import secrets
import threading
import time


class ClaudeContainer:
    def __init__(
        self,
        image=_claude_constants.IMAGE,
        profile=_claude_constants.PROFILE,
        lease_service=None,
    ):
        if not isinstance(image, str) or not re.fullmatch(r"[A-Za-z0-9_./:@-]+", image):
            raise _runtime_errors.RunnerError("claude_container_configuration_invalid")
        if not isinstance(profile, str) or not re.fullmatch(
            r"laomedo-claude-[a-z0-9-]+", profile
        ):
            raise _runtime_errors.RunnerError("claude_container_configuration_invalid")
        checked = _claude_utils.run_docker(
            ["image", "inspect", image], text=True, timeout=20
        )
        try:
            self.image_id = json.loads(checked.stdout)[0]["Id"]
            if checked.returncode or not re.fullmatch(
                r"sha256:[0-9a-f]{64}", self.image_id
            ):
                raise ValueError()
        except (ValueError, KeyError, IndexError, TypeError):
            raise _runtime_errors.RunnerError(
                "claude_container_image_missing"
            ) from None
        self.profile, self.lease_service = profile, lease_service
        self.check_supervisor()
        volume = _claude_utils.run_docker(
            ["volume", "inspect", profile], text=True, timeout=15
        )
        if volume.returncode:
            created = _claude_utils.run_docker(
                ["volume", "create", "--label", "laomedo.provider=claude", profile],
                text=True,
                timeout=15,
            )
            if created.returncode:
                raise _runtime_errors.RunnerError(
                    "claude_container_profile_unavailable"
                )
            volume = _claude_utils.run_docker(
                ["volume", "inspect", profile], text=True, timeout=15
            )
        try:
            if (
                json.loads(volume.stdout)[0]["Labels"].get("laomedo.provider")
                != "claude"
            ):
                raise ValueError()
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise _runtime_errors.RunnerError(
                "claude_container_profile_unavailable"
            ) from None
        version = self.control(["--version"], timeout=60)
        if (
            version.returncode
            or version.stdout.decode().strip()
            != _claude_constants.CLI_VERSION + " (Claude Code)"
        ):
            raise _runtime_errors.RunnerError("unsupported_claude_cli_version")

    def prefix(
        self, *, name=None, run_id=None, token=None, workspace=None, worker=False
    ):
        args = [
            "run",
            "--rm",
            "--init",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--read-only",
            "--pids-limit=128",
            "--memory=1g",
            "--cpus=2",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=256m",
            "--workdir",
            "/draft",
        ]
        if name:
            args += [
                "--name",
                name,
                "--label",
                _leases_constants.LABEL_RUN + "=" + run_id,
                "--label",
                _leases_constants.LABEL_TOKEN + "=" + token,
            ]
        if worker:
            args += [
                "--network=none",
                "--env",
                "HOME=/tmp",
                "--env",
                "CLAUDE_CONFIG_DIR=/tmp/unused",
            ]
        else:
            args += ["--mount", f"type=volume,source={self.profile},target=/profile"]
        if workspace:
            args += [
                "--mount",
                f"type=bind,source={workspace},target=/draft",
                "--mount",
                f'type=bind,source={workspace / ".agents/skills"},target=/draft/.agents/skills,readonly',
                "--mount",
                f'type=bind,source={workspace / ".agents/skills"},target=/draft/.claude/skills,readonly',
            ]
        return args

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
                <= _leases_constants.SERVICE_STALE_SECONDS
                or not -1
                <= time.monotonic() - monotonic
                <= _leases_constants.SERVICE_STALE_SECONDS
            ):
                raise ValueError()
        except (OSError, ValueError, TypeError, AttributeError):
            raise _runtime_errors.RunnerError("lease_service_unavailable") from None

    def control(self, args, *, input=None, timeout=45):
        # An in-container timeout also applies if the host process disappears.
        prefix = self.prefix() + [
            "--entrypoint",
            "timeout",
            "-i",
            self.image_id,
            "--signal=TERM",
            "--kill-after=5s",
            str(timeout),
            "claude",
            *args,
        ]
        return _claude_utils.run_docker(prefix, input=input, timeout=timeout + 10)

    def bounded_command(self, command, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _runtime_errors.RunnerError("claude_turn_timeout")
        return [
            "--entrypoint",
            "python3",
            "-i",
            self.image_id,
            "-c",
            _claude_constants.EXECUTION_GUARD,
            str(time.time() + remaining),
            str(remaining),
            *command,
        ]

    def lease(self, run_id, name, token, cancelled, scope=None):
        if self.lease_service is None:
            raise _runtime_errors.RunnerError("lease_service_required")
        try:
            return _leases_client.LeaseClient(
                self.lease_service,
                run_id=run_id,
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
            prefix = self.runtime.prefix(
                name=name,
                run_id=self.record["run_id"],
                token=token,
                workspace=self.root / "workspace",
                worker=True,
            )
            with self.active_lock:
                self.active[name] = token
            try:
                worker_deadline = min(self.deadline, time.monotonic() + 120)
                result = _claude_utils.run_docker(
                    prefix
                    + self.runtime.bounded_command(
                        ["sh", "-c", value["command"]], worker_deadline
                    ),
                    timeout=max(1, worker_deadline - time.monotonic()) + 10,
                )
                return {
                    "exit_code": result.returncode,
                    "output": (result.stdout + result.stderr)[: 1024 * 1024].decode(
                        "utf-8", errors="replace"
                    ),
                }
            finally:
                verified, _ = _leases_utils.cleanup_exact(
                    _leases_models.ContainerIdentity(
                        name=name, run_id=self.record["run_id"], token=token
                    )
                )
                if verified:
                    try:
                        lease.finish()
                    except RuntimeError:
                        _leases_utils.cleanup_exact(
                            _leases_models.ContainerIdentity(
                                name=name, run_id=self.record["run_id"], token=token
                            )
                        )
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
                    name=name, run_id=self.record["run_id"], token=token
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
