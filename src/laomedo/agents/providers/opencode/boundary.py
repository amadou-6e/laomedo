"""Separate OpenCode controller credentials from Docker command workers."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import error
from urllib import request
from uuid import uuid4
import base64
import http.client
import json
import laomedo.agents.providers.opencode.settings as _opencode_settings
import laomedo.agents.providers.opencode.utils as _opencode_utils
import laomedo.agents.runtime.errors as _runtime_errors
import laomedo.agents.runtime.utils as _runtime_utils
import secrets
import shutil
import socket
import threading
import time


class CommandBroker:
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
        self.workspace, self.canonical, self.store = workspace, canonical, store
        self.evidence = evidence
        self.token = secrets.token_hex(32)
        self.closed = self.cleanup_failed = False
        self.error_code = None
        self.stopping = threading.Event()
        self.worker_image_id = worker_image_id or _opencode_settings.WORKER_IMAGE_ID
        self.docker_endpoint = docker_endpoint
        self.receipts = (
            Path(receipt_directory)
            if receipt_directory is not None
            else evidence.joinpath("docker-receipts")
        )
        self.receipts.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.capacity = threading.BoundedSemaphore(1)
        broker = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def setup(self):
                """Bound malformed or abandoned broker uploads."""
                super().setup()
                self.connection.settimeout(5)

            def do_POST(self):
                if (
                    self.path != "/mcp"
                    or self.headers.get("Authorization") != "Bearer " + broker.token
                ):
                    self.send_error(403)
                    return
                msg = None
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 65536:
                        raise ValueError("invalid_body")
                    msg = json.loads(self.rfile.read(length))
                    if "id" not in msg:
                        self.send_response(202)
                        self.end_headers()
                        return
                    value = broker.rpc(msg.get("method"), msg.get("params", {}))
                    body = {"jsonrpc": "2.0", "id": msg["id"], "result": value}
                except Exception:
                    body = {
                        "jsonrpc": "2.0",
                        "id": msg.get("id") if isinstance(msg, dict) else None,
                        "error": {"code": -32602, "message": "broker_request_failed"},
                    }
                data = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        # Docker bridge must reach this host listener. A random bearer capability
        # is mandatory, and only one run's immutable mounts are addressable.
        self.server = ThreadingHTTPServer(("0.0.0.0", 0), Handler)
        self.server.daemon_threads = True
        try:
            self.thread = threading.Thread(
                target=self.server.serve_forever, daemon=True
            )
            self.thread.start()
        except Exception:
            self.server.server_close()
            raise

    def rpc(self, method, params):
        if method == "initialize":
            return {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "laomedo-command-worker", "version": "1"},
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {
                "tools": [
                    {
                        "name": "exec",
                        "description": "Run a shell command in the isolated /draft workspace Docker worker. Credentials are not mounted.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"command": {"type": "string"}},
                            "required": ["command"],
                            "additionalProperties": False,
                        },
                    }
                ]
            }
        if method != "tools/call" or params.get("name") != "exec":
            raise _runtime_errors.RunnerError("unknown_worker_tool")
        command = params.get("arguments", {}).get("command")
        if not isinstance(command, str) or not command.strip() or len(command) > 16000:
            raise _runtime_errors.RunnerError("invalid_worker_command")
        result = self.execute(command)
        return {
            "content": [{"type": "text", "text": json.dumps(result)}],
            "isError": result["exit_code"] != 0,
        }

    def execute(self, command):
        """Run one credential-free worker; a receipt owns all cleanup uncertainty."""
        if not self.capacity.acquire(blocking=False):
            return {"exit_code": 75, "stdout": "", "stderr": "worker_busy"}
        try:
            with self.lock:
                if self.closed:
                    raise _runtime_errors.RunnerError("opencode_command_service_closed")
            from py_docker import Client
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
            try:
                with Client(
                    environment={"DOCKER_HOST": self.docker_endpoint}
                ) as docker:
                    result = docker.jobs.run(
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
                            receipt_path=self.receipts.joinpath(name + ".json"),
                        ),
                        cancelled=self.stopping,
                    )
                value = {
                    "exit_code": result.exit_code,
                    "stdout": result.stdout.decode("utf-8", errors="replace")[:32768],
                    "stderr": result.stderr.decode("utf-8", errors="replace")[:32768],
                }
            except CleanupUnconfirmedError:
                self.cleanup_failed = True
                raise _runtime_errors.RunnerError(
                    "opencode_container_cleanup_unverified"
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
                raise _runtime_errors.RunnerError(
                    "opencode_workspace_command_failed"
                ) from None
            with self.evidence.joinpath("worker-events.jsonl").open(
                "a", encoding="utf-8"
            ) as log:
                log.write(json.dumps({"command": command, **value}) + "\n")
            return value
        finally:
            self.capacity.release()

    def stop(self):
        """Reject new work and signal exact-ID cancellation of the active job."""
        with self.lock:
            self.closed = True
            self.stopping.set()

    def close(self):
        """Cancel the active job and await its confirmed cleanup before returning."""
        self.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        acquired = self.capacity.acquire(timeout=180)
        if acquired:
            self.capacity.release()
        if not acquired or self.cleanup_failed or self.thread.is_alive():
            raise _runtime_errors.RunnerError("opencode_container_cleanup_unverified")


class IsolatedOpenCode:
    """One controller per turn, persistent session profile, independent workers."""

    def __init__(
        self,
        workspace,
        evidence,
        *,
        profile,
        image,
        image_id,
        worker_image_id=None,
        configure_agents=None,
        receipt_directory=None,
    ):
        self.termination_verified = False
        selected_worker_id = worker_image_id or _opencode_settings.WORKER_IMAGE_ID
        self.profile = _runtime_utils._private(Path(profile))
        if not (self.profile / "auth.json").is_file():
            raise _runtime_errors.RunnerError("opencode_private_auth_required")
        self.check_auth_fresh()
        identity_path = self.profile / "identity.json"
        if not identity_path.exists():
            _runtime_utils._json(identity_path, {"profile_id": str(uuid4())})
        self.runtime_identity = {
            "provider": "opencode",
            "runtime_version": _opencode_settings.CLI_VERSION,
            "image": image,
            "image_id": image_id,
            "profile_id": json.loads(identity_path.read_text())["profile_id"],
            "worker_image": _opencode_settings.WORKER_IMAGE,
            "worker_image_id": selected_worker_id,
            "credential_binding": _opencode_utils._credential_binding(self.profile),
        }
        try:
            from py_docker import Client
            from py_docker.errors import (
                CleanupUnconfirmedError, ConnectionConfigurationError,
                DockerOperationError, OwnershipConflictError,
            )
        except ImportError:
            raise _runtime_errors.RunnerError(
                "opencode_controller_startup_failed"
            ) from None
        try:
            with Client() as docker:
                self.docker_endpoint = docker.connection.endpoint
                try:
                    docker.images.resolve(image, expected_id=image_id)
                    docker.images.resolve(_opencode_settings.WORKER_IMAGE, expected_id=selected_worker_id)
                except OwnershipConflictError:
                    raise _runtime_errors.RunnerError("opencode_image_pin_mismatch") from None
                except DockerOperationError:
                    raise _runtime_errors.RunnerError("opencode_controller_image_unavailable") from None
                receipts = (
                    Path(receipt_directory)
                    if receipt_directory is not None
                    else evidence.joinpath("docker-receipts")
                )
                receipts.mkdir(mode=0o700, parents=True, exist_ok=True)
                for receipt in receipts.glob("*.json"):
                    docker.sessions.recover(receipt)
        except CleanupUnconfirmedError:
            raise _runtime_errors.RunnerError("opencode_container_cleanup_unverified") from None
        except ConnectionConfigurationError:
            raise _runtime_errors.RunnerError("opencode_container_configuration_invalid") from None
        except DockerOperationError:
            raise _runtime_errors.RunnerError("opencode_controller_startup_failed") from None
        root = evidence / ("controller-" + uuid4().hex)
        root.mkdir()
        view = root / "view"
        view.mkdir()
        # No user project configs/custom tools are ever mounted in the controller.
        shutil.copytree(workspace / ".agents", view / ".agents")
        self.broker = None
        self.log = None
        self.name = None
        self.session = self.docker = self.drainer = None
        self.drain_error = None
        self.closing = False
        try:
            self.broker = CommandBroker(
                workspace,
                evidence / "canonical",
                evidence / "store",
                evidence,
                worker_image_id=selected_worker_id,
                docker_endpoint=self.docker_endpoint,
                receipt_directory=receipts,
            )
            self.password = secrets.token_hex(32)
            self.name = "laomedo-oc-controller-" + uuid4().hex
            self.log = (evidence / "raw-events.jsonl").open("a", encoding="utf-8")
            permissions = {"*": "deny", "laomedo_exec": "allow", "skill": {"*": "deny"}}
            for skill in (view / ".agents/skills").iterdir():
                permissions["skill"][skill.name] = "allow"
            config = {
                "$schema": "https://opencode.ai/config.json",
                "autoupdate": False,
                "share": "disabled",
                "plugin": [],
                "mcp": {
                    "laomedo": {
                        "type": "remote",
                        "url": f"http://host.docker.internal:{self.broker.server.server_port}/mcp",
                        "headers": {"Authorization": "Bearer " + self.broker.token},
                        "oauth": False,
                    }
                },
                "permission": permissions,
                "tools": {"*": False, "skill": True, "laomedo_exec": True},
            }
            provider_options = self.profile / "provider-options.json"
            if provider_options.exists():
                supplied = json.loads(provider_options.read_text(encoding="utf-8"))
                organization = (
                    supplied.get("provider", {})
                    .get("opencode-go", {})
                    .get("options", {})
                    .get("headers", {})
                    .get("x-opencode-org-id")
                )
                if not isinstance(organization, str) or not organization:
                    raise _runtime_errors.RunnerError(
                        "opencode_organization_context_invalid"
                    )
                routing = supplied["provider"]["opencode-go"]
                if (
                    routing.get("api") != "https://opencode.ai/inference/go/openai/v1"
                    or routing.get("npm") != "@ai-sdk/openai-compatible"
                ):
                    raise _runtime_errors.RunnerError(
                        "opencode_console_provider_routing_not_allowed"
                    )
                config["provider"] = {
                    "opencode-go": {
                        "api": routing["api"],
                        "npm": routing["npm"],
                        "models": routing.get("models", {}),
                        "options": {"headers": {"x-opencode-org-id": organization}},
                    }
                }
            # Trusted host startup policy only, never graph/request input. Keep
            # the default isolated tools unless the operator explicitly extends
            # them (e.g. enabling a named read-only native subagent).
            if configure_agents is not None:
                configure_agents(config)
            _runtime_utils._json(root / "config.json", config)
            self.profile.joinpath("sessions").mkdir(exist_ok=True)
        except Exception:
            self.close()
            raise
        from py_docker.containers.models import ContainerSpec, Mount
        from py_docker.sessions.models import ContainerSession
        from py_docker.streams.models import StreamLimits

        try:
            self.docker = Client(environment={"DOCKER_HOST": self.docker_endpoint})
            self.session = self.docker.sessions.open(
                ContainerSession(
                    spec=ContainerSpec(
                        image=image_id,
                        name=self.name,
                        entrypoint=["timeout"],
                        command=[
                            "--signal=TERM",
                            "--kill-after=5s",
                            str(_opencode_settings.CONTROLLER_LIFETIME_SECONDS),
                            "opencode",
                            "serve",
                            "--pure",
                            "--hostname",
                            "0.0.0.0",
                            "--port",
                            "4096",
                        ],
                        user="10001:10001",
                        read_only=False,
                        network_mode="bridge",
                        working_dir="/draft",
                        ports={"4096/tcp": None},
                        extra_hosts={"host.docker.internal": "host-gateway"},
                        environment={
                            "OPENCODE_CONFIG": "/controller-config.json",
                            "OPENCODE_DISABLE_PROJECT_CONFIG": "true",
                            "OPENCODE_SERVER_PASSWORD": self.password,
                            "HOME": "/home/runner",
                            "XDG_STATE_HOME": "/tmp/opencode-state",
                            "XDG_CACHE_HOME": "/tmp/opencode-cache",
                            "XDG_CONFIG_HOME": "/tmp/opencode-config",
                        },
                        mounts=[
                            Mount(
                                type="bind",
                                source=str(source),
                                target=target,
                                read_only=readonly,
                            )
                            for source, target, readonly in (
                                (view, "/draft", True),
                                (
                                    root.joinpath("config.json"),
                                    "/controller-config.json",
                                    True,
                                ),
                                (
                                    self.profile.joinpath("sessions"),
                                    "/home/runner/.local/share/opencode",
                                    False,
                                ),
                                (
                                    self.profile.joinpath("auth.json"),
                                    "/home/runner/.local/share/opencode/auth.json",
                                    True,
                                ),
                            )
                        ],
                    ),
                    limits=StreamLimits(
                        seconds=_opencode_settings.CONTROLLER_LIFETIME_SECONDS + 10,
                        max_bytes=36 * 1024 * 1024,
                    ),
                    receipt_path=receipts.joinpath(self.name + ".json"),
                )
            )

            def drain():
                try:
                    with root.joinpath("startup.log").open("wb") as log:
                        tail = bytearray()
                        while (frame := self.session.read_frame()) is not None:
                            tail.extend(frame.data)
                            del tail[: -_opencode_settings.CONTROLLER_LOG_TAIL_BYTES]
                            log.seek(0)
                            log.write(tail)
                            log.truncate()
                            log.flush()
                except Exception:
                    if not self.closing:
                        self.drain_error = "opencode_controller_output_failed"
                        try:
                            self.session.terminate()
                        except Exception:
                            pass  # Creator-thread close retains and reports cleanup uncertainty.

            self.drainer = threading.Thread(target=drain, daemon=True)
            self.drainer.start()
            self.port = self.docker.containers.published_port(
                self.session.identity, "4096/tcp"
            )
            for _ in range(40):
                try:
                    if self.call("GET", "/global/health").get("healthy"):
                        break
                except (OSError, error.URLError):
                    if self.drain_error or not self.session.state().running:
                        raise _runtime_errors.RunnerError(
                            "opencode_controller_startup_failed"
                        )
                    time.sleep(0.25)
            else:
                raise _runtime_errors.RunnerError("opencode_controller_not_ready")
        except Exception:
            self.close()
            raise _runtime_errors.RunnerError(
                "opencode_controller_startup_failed"
            ) from None

    def open_events(self):
        basic = base64.b64encode(("opencode:" + self.password).encode()).decode()
        connection = http.client.HTTPConnection("127.0.0.1", int(self.port), timeout=30)
        connection.request(
            "GET",
            "/event?directory=/draft",
            headers={"Authorization": "Basic " + basic, "Accept": "text/event-stream"},
        )
        response = connection.getresponse()
        if response.status != 200:
            connection.close()
            raise RuntimeError("opencode_native_subscription_unavailable")
        # The owned connection is explicitly shut down by close(); a quiet model
        # step must not terminate capture at the HTTP connect timeout.
        if connection.sock is not None:
            connection.sock.settimeout(None)

        class EventStream:
            def readline(self, limit):
                return response.readline(limit)

            def close(self):
                if connection.sock is not None:
                    try:
                        connection.sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                response.close()
                connection.close()

        return EventStream()

    def check_transport(self):
        """Surface fatal capture or worker failures independently of model claims."""
        if self.drain_error:
            raise _runtime_errors.RunnerError("opencode_controller_output_failed")
        if self.broker is not None and self.broker.error_code:
            raise _runtime_errors.RunnerError(self.broker.error_code)

    def call(self, method, path, payload=None):
        if method == "POST" and path.endswith("/abort") and self.broker is not None:
            self.broker.stop()
        self.check_transport()
        basic = base64.b64encode(("opencode:" + self.password).encode()).decode()
        req = request.Request(
            "http://127.0.0.1:" + str(self.port) + path + "?directory=/draft",
            data=None if payload is None else json.dumps(payload).encode(),
            headers={
                "Authorization": "Basic " + basic,
                "Content-Type": "application/json",
            },
            method=method,
        )
        with request.urlopen(
            req, timeout=3 if path == "/global/health" else 180
        ) as response:
            raw = response.read()
            value = json.loads(raw) if raw else None
        self.check_transport()
        # Raw provider records stay in private run evidence. Request credentials
        # and config responses are never placed in the provider trace.
        if path not in {"/config", "/provider"}:
            self.log.write(
                json.dumps({"method": method, "path": path, "response": value}) + "\n"
            )
            self.log.flush()
        return value

    def close(self):
        """Close on the launch thread; uncertain controller or worker cleanup fails."""
        self.closing = True
        try:
            if self.session is not None:
                self.session.close()
                if self.session.cleanup_confirmed is not True:
                    raise _runtime_errors.RunnerError("opencode_container_cleanup_unverified")
            if self.drainer is not None:
                self.drainer.join(5)
                if self.drainer.is_alive():
                    raise _runtime_errors.RunnerError(
                        "opencode_container_cleanup_unverified"
                    )
        except Exception:
            raise _runtime_errors.RunnerError(
                "opencode_container_cleanup_unverified"
            ) from None
        finally:
            try:
                if self.broker is not None:
                    self.broker.close()
                    self.broker = None
            finally:
                if self.docker is not None:
                    self.docker.close()
                    self.docker = None
                if self.log is not None:
                    self.log.close()
                    self.log = None
        self.session = None
        self.termination_verified = True
        self.check_transport()

    def check_auth_fresh(self):
        _opencode_utils.check_auth_fresh(self.profile)
