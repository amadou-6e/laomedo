"""Separate OpenCode controller credentials from Docker command workers."""

from __future__ import annotations

import asyncio
from .http.server import BrokerHttpServer
from pathlib import Path
from uuid import uuid4
import json
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
import secrets
import shutil
import threading


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
        self.worker_image_id = worker_image_id or WORKER_IMAGE_ID
        self.docker_endpoint = docker_endpoint
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

        # Docker bridge must reach this host listener. A random bearer capability
        # is mandatory, and only one run's immutable mounts are addressable.
        self.server = BrokerHttpServer(self, ("0.0.0.0", 0))
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
            raise RunnerError("unknown_worker_tool")
        command = params.get("arguments", {}).get("command")
        if not isinstance(command, str) or not command.strip() or len(command) > 16000:
            raise RunnerError("invalid_worker_command")
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
                    raise RunnerError("opencode_command_service_closed")
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
            receipt_path = self.receipts.joinpath(name + ".json")
            with self.lock:
                self.allocated_receipts.add(receipt_path)
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
                            receipt_path=receipt_path,
                        ),
                        cancelled=self.stopping,
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
        self.drained = acquired and not self.thread.is_alive()
        if not acquired or self.cleanup_failed or self.thread.is_alive():
            raise RunnerError("opencode_container_cleanup_unverified")


# TODO! the adjective is unnecessary giving the naming nomenclature. This file should not be named boundary and should probably not group both objects
class IsolatedOpenCode:
    """One controller per turn, persistent session profile, independent workers."""

    @property
    def runtime_identity(self):
        """Preserve the provider's public dictionary fingerprint boundary."""
        return self.identity.to_payload()

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
        self.cleanup_observed = None
        self.broker = self.session = self.docker = None
        self.receipts = None
        self.allocated_receipts = set()
        self.closing = False
        selected_worker_id = worker_image_id or WORKER_IMAGE_ID
        self.profile = _private(Path(profile))
        if not (self.profile / "auth.json").is_file():
            raise RunnerError("opencode_private_auth_required")
        self.check_auth_fresh()
        identity_path = self.profile / "identity.json"
        if not identity_path.exists():
            _json(identity_path, {"profile_id": str(uuid4())})
        self.identity = OpenCodeRuntimeIdentity(
            runtime_version=CLI_VERSION,
            image=image,
            image_id=image_id,
            profile_id=json.loads(identity_path.read_text())["profile_id"],
            worker_image=WORKER_IMAGE,
            worker_image_id=selected_worker_id,
            credential_binding=_credential_binding(self.profile),
        )
        try:
            from py_docker import Client
            from py_docker.errors import (
                CleanupUnconfirmedError,
                ConnectionConfigurationError,
                DockerOperationError,
                OwnershipConflictError,
                ImageResolutionError,
            )
        except ImportError:
            raise RunnerError("opencode_controller_startup_failed") from None
        try:
            with Client() as docker:
                self.docker_endpoint = docker.connection.endpoint
                docker.images.resolve(image, expected_id=image_id)
                docker.images.resolve(WORKER_IMAGE, expected_id=selected_worker_id)
                receipts = (
                    Path(receipt_directory)
                    if receipt_directory is not None
                    else evidence.joinpath("docker-receipts")
                )
                receipts.mkdir(mode=0o700, parents=True, exist_ok=True)
                self.receipts = receipts
                for receipt in receipts.glob("*.json"):
                    docker.sessions.recover(receipt)
        except OwnershipConflictError:
            raise RunnerError("opencode_image_pin_mismatch") from None
        except ImageResolutionError:
            raise RunnerError("opencode_controller_image_unavailable") from None
        except CleanupUnconfirmedError:
            raise RunnerError("opencode_container_cleanup_unverified") from None
        except ConnectionConfigurationError:
            raise RunnerError("opencode_container_configuration_invalid") from None
        except DockerOperationError:
            raise RunnerError("opencode_controller_startup_failed") from None
        root = evidence / ("controller-" + uuid4().hex)
        root.mkdir()
        view = root / "view"
        view.mkdir()
        # No user project configs/custom tools are ever mounted in the controller.
        shutil.copytree(workspace / ".agents", view / ".agents")
        self.broker = None
        self.name = None
        self.session = self.docker = None
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
            self.name = "laomedo-oc-controller-" + uuid4().hex
            permissions = {"*": "deny", "laomedo_exec": "allow", "skill": {"*": "deny"}}
            for skill in (view / ".agents/skills").iterdir():
                permissions["skill"][skill.name] = "allow"
            config = OpenCodeConfig(
                permissions=permissions,
                broker_port=self.broker.server.server_port,
                broker_token=self.broker.token,
            ).to_config()
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
                    raise RunnerError("opencode_organization_context_invalid")
                routing = supplied["provider"]["opencode-go"]
                if (
                    routing.get("api") != "https://opencode.ai/inference/go/openai/v1"
                    or routing.get("npm") != "@ai-sdk/openai-compatible"
                ):
                    raise RunnerError("opencode_console_provider_routing_not_allowed")
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
            _json(root / "config.json", config)
            self.profile.joinpath("sessions").mkdir(exist_ok=True)
        except Exception:
            self.close()
            raise
        from py_docker.containers.models import ContainerSpec, Mount

        self.root, self.evidence, self.receipts = root, evidence, receipts
        self.spec = ContainerSpec(
            image=image_id,
            name=self.name,
            entrypoint=["timeout"],
            command=[
                "--signal=TERM",
                "--kill-after=5s",
                str(CONTROLLER_LIFETIME_SECONDS),
                "opencode",
                "acp",
            ],
            user="10001:10001",
            read_only=False,
            network_mode="bridge",
            working_dir="/draft",
            stdin_open=True,
            extra_hosts={"host.docker.internal": "host-gateway"},
            environment={
                "OPENCODE_CONFIG": "/controller-config.json",
                "OPENCODE_DISABLE_PROJECT_CONFIG": "true",
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
        )
        try:
            self.docker = Client(environment={"DOCKER_HOST": self.docker_endpoint})
        except Exception as error:
            observation = failure_observation(
                error, stage="startup", code="opencode_controller_startup_failed"
            )
            try:
                self.close()
            except RunnerError as cleanup:
                raise RunnerError(
                    cleanup.code, observation=observation or cleanup.observation
                ) from None
            raise RunnerError(
                "opencode_controller_startup_failed", observation=observation
            ) from None

    def models(self):
        """Read native CLI metadata without creating a session or model turn."""
        from py_docker.jobs.models import ContainerJob
        from py_docker.streams.models import StreamLimits
        from py_docker.errors import DockerOperationError, CleanupUnconfirmedError

        name = "laomedo-oc-catalog-" + uuid4().hex
        self.check_auth_fresh()
        receipt_path = self.receipts.joinpath(name + ".json")
        self.allocated_receipts.add(receipt_path)
        try:
            result = self.docker.jobs.run(
                ContainerJob(
                    spec=self.spec.model_copy(
                        update={
                            "name": name,
                            "stdin_open": False,
                            "command": [
                                "--signal=TERM",
                                "--kill-after=5s",
                                "60",
                                "opencode",
                                "models",
                                "--verbose",
                            ],
                        }
                    ),
                    limits=StreamLimits(seconds=70, max_bytes=8 * 1024 * 1024),
                    wait_timeout_seconds=10.0,
                    receipt_path=receipt_path,
                )
            )
            if result.exit_code:
                raise RunnerError("opencode_model_not_connected")
            return model_metadata(result.stdout.decode("utf-8"))
        except CleanupUnconfirmedError as error:
            raise RunnerError(
                "opencode_container_cleanup_unverified",
                observation=failure_observation(
                    error, stage="cleanup", code="opencode_container_cleanup_unverified"
                ),
            ) from None
        except DockerOperationError as error:
            raise RunnerError(
                "opencode_controller_startup_failed",
                observation=failure_observation(
                    error, stage="startup", code="opencode_controller_startup_failed"
                ),
            ) from None

    def history_reader(self):
        """Bind an offline metadata reader without mounting credentials or live state."""
        from laomedo.agents.agents.opencode.history.models import HistorySource
        from laomedo.agents.agents.opencode.history.reader import HistoryReader

        return HistoryReader(
            HistorySource(
                store=self.profile / "sessions",
                image_id=self.identity.image_id,
                endpoint=self.docker_endpoint,
                receipts=self.receipts,
            ),
            self.evidence,
        )

    def run(self, task, *, model, session_id, cancelled, capture, on_session):
        """Execute over shared ACP; no published port, password or SSE reader."""
        from py_docker.sessions.models import ContainerSession
        from py_docker.streams.models import StreamLimits

        self.check_auth_fresh()
        receipt_path = self.receipts.joinpath(self.name + ".json")
        self.allocated_receipts.add(receipt_path)
        self.session = self.docker.sessions.open(
            ContainerSession(
                spec=self.spec,
                limits=StreamLimits(
                    seconds=CONTROLLER_LIFETIME_SECONDS + 10,
                    max_bytes=36 * 1024 * 1024,
                ),
                receipt_path=receipt_path,
            )
        )
        return asyncio.run(
            self._run_acp(task, model, session_id, cancelled, capture, on_session)
        )

    async def _run_acp(self, task, model, session_id, cancelled, capture, on_session):
        """Validate agent identity, load the same native session and await its prompt."""
        from laomedo.agents.agents.base.acp.session import AcpSession

        # Loading may replay earlier native history. Subscribe only after the
        # current attempt is bound so it cannot be mistaken for new activity.
        client = AcpSession(self.session)
        try:
            initialized = await client.initialize()
            if initialized.agent_info.version != CLI_VERSION:
                raise RunnerError("opencode_runtime_pin_mismatch")
            created = await client.open(session_id=session_id)
            options = getattr(created, "config_options", None) or []
            picker = next(
                (option for option in options if option.category == "model"), None
            )
            if picker is None:
                raise RunnerError("opencode_model_not_connected")
            configured = await client.configure(picker.id, model)
            observed = next(
                (
                    option.current_value
                    for option in configured.config_options
                    if option.id == picker.id
                ),
                None,
            )
            if observed != model:
                raise RunnerError("opencode_model_not_connected")
            on_session(client.session_id)
            capture.begin(client.session_id, task)
            client.on_update = capture.update
            outcome = await client.prompt(task, cancelled=cancelled, seconds=180)
            if not cancelled.is_set():
                self.check_transport()
            status = (
                "cancelled"
                if cancelled.is_set() or outcome.stop_reason == "cancelled"
                else "completed" if outcome.stop_reason == "end_turn" else "failed"
            )
            capture.finish(client.session_id, status, outcome.usage)
            if status == "failed":
                raise RunnerError("opencode_response_not_terminal")
            return outcome
        finally:
            await client.close()

    def cancel(self):
        """Stop owned workers; the shared ACP prompt observes the runner's flag."""
        if self.broker is not None:
            self.broker.stop()

    def check_transport(self):
        """Surface independently observed worker failures, never model claims."""
        if self.broker is not None and self.broker.error_code:
            raise RunnerError(self.broker.error_code)

    def close(self):
        """Confirm exact controller and worker cleanup on the lifecycle creator."""
        if self.closing:
            if not self.termination_verified:
                raise RunnerError("opencode_container_cleanup_unverified")
            return
        self.closing = True
        failed = False
        observation = None
        drained = self.broker is None
        recovered = True
        try:
            if self.broker is not None:
                self.broker.stop()
        except Exception as error:
            failed = True
            observation = failure_observation(
                error, stage="cleanup", code="opencode_container_cleanup_unverified"
            )
        try:
            if self.session is not None:
                self.session.close()
        except Exception as error:
            failed = True
            observation = observation or failure_observation(
                error, stage="cleanup", code="opencode_container_cleanup_unverified"
            )
        try:
            if self.broker is not None:
                self.broker.close()
            drained = True
        except Exception as error:
            failed = True
            drained = self.broker is not None and self.broker.drained is True
            observation = observation or failure_observation(
                error, stage="cleanup", code="opencode_container_cleanup_unverified"
            )
        finally:
            paths = set(self.allocated_receipts)
            if self.broker is not None:
                with self.broker.lock:
                    paths.update(self.broker.allocated_receipts)
            if paths and (not drained or self.docker is None):
                failed, recovered = True, False
            elif paths:
                for receipt in paths:
                    try:
                        self.docker.sessions.recover(receipt)
                    except Exception as error:
                        failed, recovered = True, False
                        observation = observation or failure_observation(
                            error,
                            stage="cleanup",
                            code="opencode_container_cleanup_unverified",
                        )
            self.cleanup_observed = drained and recovered
            if self.docker is not None:
                try:
                    self.docker.close()
                except Exception as error:
                    failed = True
                    observation = observation or failure_observation(
                        error,
                        stage="cleanup",
                        code="opencode_container_cleanup_unverified",
                    )
        if failed:
            raise RunnerError(
                "opencode_container_cleanup_unverified", observation=observation
            ) from None
        self.termination_verified = True

    def check_auth_fresh(self):
        """Validate the dedicated profile's existing bounded credential grant."""
        opencode_check_auth_fresh(self.profile)
