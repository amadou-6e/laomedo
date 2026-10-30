"""Codex adapter for the provider-neutral Agent lifecycle."""

from __future__ import annotations
from laomedo.agents.agents.codex.settings import CLI_VERSION
from laomedo.agents.agents.codex.settings import CONFIG
from laomedo.agents.agents.codex.settings import CONFIG_LF_SHA256
from laomedo.agents.agents.codex.settings import CONFIG_SHA256
from laomedo.agents.agents.codex.settings import GIT_IMAGE
from laomedo.agents.agents.codex.settings import GIT_IMAGE_ID
from laomedo.agents.agents.codex.settings import IMAGE
from laomedo.agents.agents.codex.settings import IMAGE_ID
from laomedo.agents.agents.codex.settings import NATIVE_TURN_SECONDS
from laomedo.agents.agents.codex.settings import PREFLIGHT_API_TIMEOUT_SECONDS
from laomedo.agents.agents.codex.settings import PREFLIGHT_MAX_OUTPUT_BYTES
from laomedo.agents.agents.codex.settings import PREFLIGHT_RECEIPT_FILENAME
from laomedo.agents.agents.codex.settings import PREFLIGHT_STREAM_SECONDS
from laomedo.agents.agents.codex.settings import PREFLIGHT_WAIT_SECONDS
from laomedo.agents.agents.codex.settings import VOLUME
from laomedo.agents.agents.codex.settings import _CATALOG_INIT_LOCK
from laomedo.agents.agents.codex.utils import _answer
from laomedo.agents.agents.codex.utils import _auth_record_error
from laomedo.agents.agents.codex.utils import _command_summary
from laomedo.agents.agents.codex.utils import _ensure_split_profile
from laomedo.agents.agents.codex.utils import _execution_evidence
from laomedo.agents.agents.codex.utils import _native_error_summary
from laomedo.agents.agents.codex.utils import _split_profile
from laomedo.agents.agents.codex.controller.settings import Settings

from pathlib import Path
from uuid import uuid4
import hashlib
import asyncio
import logging
import json
from laomedo.agents.interface.output.utils import evaluate
from laomedo.agents.errors import RunnerError
from laomedo.agents.agents.codex.controller.service import CodexController
from laomedo.agents.workspaces.utils import _hash_tree
from laomedo.agents.agents.base.utils import _id
from laomedo.agents.agents.base.utils import _json
from laomedo.host.credentials.siwc.connection import ChatGPTConnection
from laomedo.host.credentials.siwc.errors import AuthError
from laomedo.host.credentials.siwc.utils import _outside_git
from laomedo.host.leases.client import LeaseClient
from laomedo.host.leases.models import ContainerIdentity
from laomedo.host.leases.utils import cleanup_exact
from laomedo.host.mediation.authority import RunGrantAuthority
from laomedo.skills.workspace.utils import verify
import re
import shutil
import threading
import time


from laomedo.agents.agents.base.agent import BaseAgent
from laomedo.agents.agents.base.models import CredentialBinding
from laomedo.agents.agents.base.models import RuntimeBinding


class CodexAgent(BaseAgent):
    provider = "codex"

    def __init__(
        self,
        state: Path,
        skill_store: Path,
        source_workspace: Path,
        *,
        transport=CodexController,
        check_docker: bool = True,
        supervise_containers: bool | None = None,
        lease_service: Path | None = None,
        github_authority: RunGrantAuthority | None = None,
        mediator_state: Path | None = None,
        git_workspace: bool = False,
        split_executor: bool = False,
        split_provider_config=(),
        split_access_token=None,
        auth_store: Path | None = None,
        publication_controller=None,
        image_id: str | None = None,
        artifact_sources=None,
    ):
        self.image = GIT_IMAGE if git_workspace else IMAGE
        self.image_id = GIT_IMAGE_ID if git_workspace else IMAGE_ID
        if image_id is not None:
            if (
                git_workspace
                or split_executor
                or not isinstance(image_id, str)
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id)
            ):
                raise RunnerError("invalid_local_image_id")
            # Trusted host startup configuration, never a per-run API input.
            self.image_id = image_id
        self.supervise_containers = (
            transport is CodexController and not split_executor
            if supervise_containers is None
            else supervise_containers
        )
        if split_executor and self.supervise_containers:
            raise RunnerError("split_executor_lease_unavailable")
        if git_workspace and split_executor:
            raise RunnerError("git_workspace_split_unsupported")
        super().__init__(
            state,
            skill_store,
            source_workspace,
            lease_service=lease_service,
            github_authority=github_authority,
            mediator_state=mediator_state,
            git_workspace=git_workspace,
            publication_controller=publication_controller,
            artifact_sources=artifact_sources,
        )
        self.transport = transport
        self.split_executor = split_executor
        self.split_provider_config = tuple(split_provider_config)
        self.split_access_token = split_access_token
        if auth_store is not None and not split_executor:
            raise RunnerError("app_owned_auth_requires_split_executor")
        if auth_store is not None and (split_provider_config or split_access_token):
            raise RunnerError("conflicting_split_auth_sources")
        if auth_store is not None:
            auth_root = _outside_git(auth_store)
            if (
                auth_root == self.state
                or auth_root.is_relative_to(self.state)
                or self.state.is_relative_to(auth_root)
                or auth_root == self.store.root
                or auth_root.is_relative_to(self.store.root)
                or self.store.root.is_relative_to(auth_root)
            ):
                raise RunnerError("auth_store_overlaps_runner_state")
            self.auth = ChatGPTConnection(auth_root)
        else:
            self.auth = None
        if self.auth:
            self.split_provider_config = (
                'model_provider="openai_chatgpt_plan"',
                'model_providers.openai_chatgpt_plan.name="ChatGPT plan"',
                'model_providers.openai_chatgpt_plan.base_url="https://api.openai.com/v1"',
                'model_providers.openai_chatgpt_plan.env_key="ACCESS_TOKEN"',
                'model_providers.openai_chatgpt_plan.wire_api="responses"',
                "model_providers.openai_chatgpt_plan.requires_openai_auth=false",
                "model_providers.openai_chatgpt_plan.supports_websockets=false",
            )
        self.profile = _split_profile(self.state) if split_executor else VOLUME
        if split_executor and transport is not CodexController:
            raise RunnerError("split_executor_requires_native_transport")
        if (
            self.split_provider_config or split_access_token is not None
        ) and not split_executor:
            raise RunnerError("split_provider_requires_split_executor")
        # The checked-in policy is LF on Linux and CRLF in Windows worktrees.
        # Accept only these two reviewed byte representations of the same policy.
        if hashlib.sha256(CONFIG.read_bytes()).hexdigest() not in {
            CONFIG_SHA256,
            CONFIG_LF_SHA256,
        }:
            raise RunnerError("permission_config_changed")
        self.docker_environment = None
        if check_docker:
            self.docker_environment = self._check_container()
            if split_executor:
                _ensure_split_profile(
                    self.profile, state=self.state, env=self.docker_environment
                )
            else:
                from py_docker import Client

                with Client(environment=self.docker_environment) as docker:
                    if not docker.volumes.exists(VOLUME):
                        raise RunnerError("docker_control_failed")

    def _check_container(self) -> dict[str, str]:
        """Recover and verify the Docker runtime without credentials or model work.

        Returns
        -------
        dict[str, str]
            Private host environment with the selected local daemon pinned.

        Raises
        ------
        RunnerError
            Existing image, CLI, configuration or cleanup refusal. Cleanup
            uncertainty wins and retains the receipt; no implicit retry occurs.
        """
        try:
            from docker.errors import DockerException
            from requests.exceptions import RequestException
            from py_docker import Client
            from py_docker.connection.settings import ConnectionSettings
            from py_docker.containers.models import ContainerSpec
            from py_docker.errors import (
                CleanupUnconfirmedError,
                ConnectionConfigurationError,
                DockerOperationError,
                OwnershipConflictError,
            )
            from py_docker.jobs.models import ContainerJob
            from py_docker.streams.models import StreamLimits
        except ImportError:
            logging.getLogger(__name__).warning(
                "Local Docker runtime dependencies are missing. Install Laomedo's "
                "runner extra in the Python environment used to start this runner "
                "(python -m pip install -e '.[runner]')."
            )
            raise RunnerError("runner_docker_check_unconfirmed") from None
        snapshot = ConnectionSettings.environment_snapshot(None)
        try:
            with Client(
                settings=ConnectionSettings(
                    timeout_seconds=PREFLIGHT_API_TIMEOUT_SECONDS
                ),
                environment=snapshot,
            ) as client:
                receipt = self.state.joinpath(PREFLIGHT_RECEIPT_FILENAME)
                client.jobs.recover(receipt)
                self._recover_containers(client)
                try:
                    client.images.resolve(self.image, expected_id=self.image_id)
                except OwnershipConflictError:
                    raise RunnerError("docker_image_digest_changed") from None
                result = client.jobs.run(
                    ContainerJob(
                        spec=ContainerSpec(
                            image=self.image_id,
                            name="laomedo-codex-preflight-" + uuid4().hex,
                            command=["codex", "--version"],
                            user="10001:10001",
                        ),
                        limits=StreamLimits(
                            seconds=PREFLIGHT_STREAM_SECONDS,
                            max_bytes=PREFLIGHT_MAX_OUTPUT_BYTES,
                        ),
                        receipt_path=receipt,
                        wait_timeout_seconds=PREFLIGHT_WAIT_SECONDS,
                    )
                )
                try:
                    version = result.stdout.decode("utf-8").strip()
                except UnicodeDecodeError:
                    raise RunnerError("unsupported_codex_cli_version") from None
                if result.exit_code != 0 or version != CLI_VERSION:
                    raise RunnerError("unsupported_codex_cli_version")
                pinned = {
                    key: value
                    for key, value in snapshot.items()
                    if key.upper() not in {"DOCKER_HOST", "DOCKER_CONTEXT"}
                }
                pinned["DOCKER_HOST"] = client.connection.endpoint
                return pinned
        except RunnerError:
            raise
        except CleanupUnconfirmedError:
            raise RunnerError("container_termination_unverified") from None
        except ConnectionConfigurationError:
            logging.getLogger(__name__).warning(
                "Docker endpoint selection was rejected: use one unambiguous local "
                "DOCKER_HOST or DOCKER_CONTEXT; TLS and remote endpoints are unsupported "
                "by this local trial. No configuration values are logged."
            )
            raise RunnerError("runner_docker_check_unconfirmed") from None
        except (
            DockerOperationError,
            DockerException,
            RequestException,
            OSError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
        ):
            raise RunnerError("runner_docker_check_unconfirmed") from None

    def _recover_containers(self, client) -> None:
        """Recover central and legacy receipts on the selected client.

        Parameters
        ----------
        client : py_docker.Client
            Endpoint-bound client; recovery refuses uncertain or active receipts.
        """
        for pending in self.state.joinpath("receipts").glob("*.json"):
            client.sessions.recover(pending)
        for folder in ("runs", "catalog", "preflight"):
            for pending in self.state.joinpath(folder).glob("*/*receipt*.json"):
                client.sessions.recover(pending)

    def runtime_binding(self):
        return RuntimeBinding(
            provider=self.provider,
            profile=self.profile,
            image=self.image,
            image_id=self.image_id,
            execution_mode="codex_acp_split" if self.split_executor else "codex_acp",
            cli_version=CLI_VERSION,
            config_sha256=CONFIG_SHA256,
            credential=(
                CredentialBinding(
                    credential_mode="chatgpt_plan_oauth",
                    credential_ref=None,
                    auth_outcome="not_checked",
                )
                if self.auth
                else None
            ),
        )

    @property
    def supports_mediated_github(self):
        return self.supervise_containers and not self.split_executor

    def recover_interrupted(self, record):
        owner = record.get("container_ownership") or {}
        if owner.get("supervised"):
            verified, detail = cleanup_exact(
                ContainerIdentity(
                    name=owner["name"],
                    run_id=record["run_id"],
                    token=owner["launch_token"],
                    docker_endpoint=owner.get("docker_endpoint"),
                )
            )
            owner["cleanup_verified"], owner["cleanup_detail"] = verified, detail
            if not verified:
                record["error_category"] = "container_cleanup_unverified"

    def _receipt_path(self, root: Path) -> Path:
        """Keep lifecycle intent outside disposable metadata and evidence folders."""
        directory = self.state.joinpath("receipts")
        directory.mkdir(mode=0o700, exist_ok=True)
        return directory.joinpath(root.name + "-controller.json")

    def _pending_receipts(self, root: Path) -> bool:
        """Retain evidence for either unresolved controller or executor cleanup."""
        return any(self.state.joinpath("receipts").glob(root.name + "-*.json")) or any(
            root.glob("*receipt*.json")
        )

    def _open_server(
        self,
        root: Path,
        *,
        access_token=None,
        lifetime_seconds: float = 60,
        name: str | None = None,
        run_id: str | None = None,
        launch_token: str | None = None,
        capability: Path | None = None,
        mediator_url: str | None = None,
        mediator_instance: str | None = None,
        repository: str | None = None,
        branch: str | None = None,
        base_branch: str = "main",
    ):
        workspace, canonical, store_mount = (
            root / name for name in ("workspace", "canonical", "store")
        )
        command_directory = None
        if capability is not None and self.git_workspace:
            from laomedo.host.mediation.agent_cli import configure_remote
            from laomedo.host.mediation.agent_cli import prepare_commands

            if repository is None or branch is None:
                raise RunnerError("mediated_command_scope_missing")
            command_directory = prepare_commands(root, repository, branch)
            # The checkout was prepared without a provider remote. This is a
            # credential-free helper URL, not an HTTPS fallback.
            configure_remote(workspace, repository)
        from laomedo.agents.agents.codex.controller.models import CodexLaunch

        values = dict(
            workspace=workspace,
            canonical=canonical,
            store_mount=store_mount,
            image=self.image_id,
            profile=self.profile,
            run_id=run_id,
            launch_token=launch_token,
            capability=capability,
            mediator_url=mediator_url,
            mediator_instance=mediator_instance,
            command_directory=command_directory,
            repository=repository,
            branch=branch,
            base_branch=base_branch,
        )
        if name is not None:
            values["name"] = name
        launch = CodexLaunch(**values)
        from laomedo.agents.agents.codex.controller.models import SplitPolicy

        if isinstance(self.transport, type) and issubclass(
            self.transport, CodexController
        ):
            split = (
                SplitPolicy(
                    provider_config=self.split_provider_config,
                    access_token=(
                        access_token
                        if access_token is not None
                        else self.split_access_token
                    ),
                )
                if self.split_executor
                else None
            )
            return self.transport(
                launch,
                root,
                env=self.docker_environment,
                lifetime_seconds=lifetime_seconds,
                receipt_path=self._receipt_path(root),
                split=split,
                secret_redactions=(
                    (capability.read_text(encoding="utf-8").strip(),)
                    if capability is not None
                    else ()
                ),
            )
        return self.transport(launch, root)

    def model_catalog(self) -> dict:
        """Serialize and briefly cache metadata discovery; never submit a turn."""
        # Lazy initialization also supports existing host-created runner objects.
        with _CATALOG_INIT_LOCK:
            if not hasattr(self, "_catalog_lock"):
                self._catalog_lock = threading.Lock()
                self._catalog_cached = None
        with self._catalog_lock:
            cached = self._catalog_cached
            if cached and time.monotonic() - cached[0] < 30:
                return cached[1]
            result = asyncio.run(self._model_catalog())
            self._catalog_cached = (time.monotonic(), result)
            return result

    async def _model_catalog(self):
        root = self.state / "catalog" / str(uuid4())
        server = None
        try:
            for name in ("workspace", "canonical", "store"):
                (root / name).mkdir(parents=True)
            token = self.auth.access_token()[0] if self.auth else None
            server = self._open_server(
                root,
                access_token=token,
                lifetime_seconds=60 + Settings.load().startup_margin,
            )
            await server.initialize()
            return {"models": await server.models(), "submitted_turns": 0}
        finally:
            try:
                if server is not None:
                    await server.close()
            finally:
                if not self._pending_receipts(root):
                    shutil.rmtree(root, ignore_errors=True)

    def preflight(self) -> dict:
        """Run provider handshake and policy probes without a model request."""
        return asyncio.run(self._preflight())

    async def _preflight(self) -> dict:
        """Launch native handshake, model and permission probes without a model turn.

        This active check starts a controller and uses a disposable workspace.
        Provider-neutral Docker startup validation is performed separately by
        the constructor; this method checks the Codex protocol and permissions.
        """
        root = self.state / "preflight" / str(uuid4())
        root.mkdir(parents=True)
        for name in ("workspace", "canonical", "store"):
            (root / name).mkdir()
        (root / "canonical/sentinel.txt").write_text(
            "CANONICAL-ORIGINAL", encoding="utf-8"
        )
        (root / "store/sentinel.txt").write_text("STORE-ORIGINAL", encoding="utf-8")
        server = None
        try:
            token = self.auth.access_token()[0] if self.auth else None
            server = self._open_server(
                root,
                access_token=token,
                lifetime_seconds=160 + Settings.load().startup_margin,
            )
            await server.initialize()
            models = await server.models()
            checks = {}
            for label in (
                "workspace_write",
                "canonical_write",
                "store_write",
                "auth_read",
            ):
                checks[label] = await server.preflight(label)
            if self.git_workspace:
                checks["git_binary"] = await server.preflight("git_binary")
                if checks["git_binary"] != 0:
                    raise RunnerError("git_image_missing_git")
            if not (
                checks["workspace_write"] == 0
                and all(
                    checks[x] not in (None, 0)
                    for x in ("canonical_write", "store_write", "auth_read")
                )
                and (root / "workspace/canary.txt").read_text() == "CANARY"
                and (root / "canonical/sentinel.txt").read_text()
                == "CANONICAL-ORIGINAL"
                and (root / "store/sentinel.txt").read_text() == "STORE-ORIGINAL"
            ):
                raise RunnerError("permission_preflight_failed")
            return {
                "status": "ready",
                "models": models,
                "image": self.image,
                "image_id": self.image_id,
                "cli_version": CLI_VERSION,
                "profile": self.profile,
                "config_sha256": CONFIG_SHA256,
                "permission_checks": checks,
                "submitted_turns": 0,
            }
        finally:
            if server is not None:
                await server.close()

    def resume(
        self,
        run_id: str,
        task: str,
        *,
        expected_post_run_hash: str,
        expected_thread_id: str,
        model: str,
        effort: str,
        activity_attempt_id: str | None = None,
    ) -> dict:
        record = self.status(run_id)
        if (
            self.publication_controller is not None
            and run_id in self.publication_controller.owned
        ):
            raise RunnerError("publication_handoff_resume_denied")
        if not isinstance(task, str) or not task.strip():
            raise RunnerError("invalid_task")
        if (
            record["status"] != "completed"
            or not record["thread_id"]
            or record["thread_id"] != expected_thread_id
            or record["post_run_hash"] != expected_post_run_hash
            or record["requested_model"] != model
            or record["requested_effort"] != effort
            or record["profile"] != self.profile
            or record.get("workspace_mode", "files")
            != ("git" if self.git_workspace else "files")
            or record.get("execution_mode", "legacy")
            != ("codex_acp_split" if self.split_executor else "codex_acp")
            or record["image"] != self.image
            or record["image_id"] != self.image_id
            or record["cli_version"] != CLI_VERSION
            or record["config_sha256"] != CONFIG_SHA256
        ):
            raise RunnerError("resume_binding_mismatch")
        run_dir = self._run_dir(run_id)
        if activity_attempt_id is not None:
            if not isinstance(activity_attempt_id, str):
                raise RunnerError("invalid_activity_attempt_id")
            _id(activity_attempt_id)
            if (
                run_dir / "activity-attempts" / (activity_attempt_id + ".json")
            ).exists():
                raise RunnerError("activity_attempt_already_exists")
        snapshot = run_dir / "post-run"
        workspace = run_dir / "workspace"
        if not snapshot.exists() or _hash_tree(snapshot) != expected_post_run_hash:
            raise RunnerError("post_run_snapshot_mismatch")
        if (
            _hash_tree(workspace, exclude_root_git=self.git_workspace)
            != expected_post_run_hash
        ):
            raise RunnerError("workspace_changed_since_snapshot")
        if (
            _hash_tree(run_dir / "canonical") != record["source_hash"]
            or (run_dir / "store/sentinel.txt").read_text(encoding="utf-8")
            != "STORE-ORIGINAL"
        ):
            raise RunnerError("protected_mount_changed")
        if self.auth:
            if record.get("runner_instance_id") != self.instance_id:
                raise RunnerError("resume_after_runner_restart_forbidden")
            _token, current = self.auth.access_token()
            prior = record.get("credential") or {}
            if any(
                current.get(key) != prior.get(key)
                for key in ("credential_ref", "provider_subject_hash")
            ):
                raise RunnerError("resume_auth_identity_mismatch")
        return self._execute(
            run_id, task, resume=True, activity_attempt_id=activity_attempt_id
        )

    def _execute(
        self,
        run_id: str,
        task: str,
        *,
        resume: bool,
        activity_attempt_id: str | None = None,
    ) -> dict:
        return asyncio.run(
            self._execute_acp(
                run_id, task, resume=resume, activity_attempt_id=activity_attempt_id
            )
        )

    async def _execute_acp(
        self,
        run_id: str,
        task: str,
        *,
        resume: bool,
        activity_attempt_id: str | None = None,
    ) -> dict:
        if activity_attempt_id is not None:
            if not isinstance(activity_attempt_id, str):
                raise RunnerError("invalid_activity_attempt_id")
            _id(activity_attempt_id)
        if not self.lock.acquire(blocking=False):
            raise RunnerError("runner_busy")
        run_dir, record, cancelled, server, lease = None, None, None, None, None
        evidence_offset, attempt_turn_offset = 0, 0
        launch_attempted = False
        activity_start = None
        activity_attempt = None
        try:
            run_dir = self._run_dir(run_id)
            with self.control_lock:
                record = self.status(run_id)
                record.setdefault("precheck", {"installed": False, "call_count": 0})
                if record["status"] == "cancelled" and record.get("cancel_confirmed"):
                    return record
                if (not resume and record["status"] != "prepared") or (
                    resume and record["status"] != "completed"
                ):
                    raise RunnerError("run_not_dispatchable")
                cancelled = threading.Event()
                evidence_offset = (run_dir / "raw-events.jsonl").stat().st_size
                attempt_turn_offset = len(record["turns"])
                from laomedo.agents.activity.runner.feed import line_count
                from laomedo.agents.activity.runner.feed import read_feed

                activity_start = (
                    line_count(run_dir / "activity-events.jsonl"),
                    line_count(run_dir / "otel-events.jsonl"),
                )
                attempt_id = (
                    activity_attempt_id
                    if resume
                    else record.get("activity_initial_attempt_id")
                ) or str(uuid4())
                attempts = run_dir / "activity-attempts"
                attempts.mkdir(exist_ok=True)
                if (attempts / (attempt_id + ".json")).exists():
                    raise RunnerError("activity_attempt_already_exists")
                activity_attempt = {
                    "id": attempt_id,
                    "native_start": activity_start[0],
                    "otel_start": activity_start[1],
                    "native_end": None,
                    "otel_end": None,
                    "fresh_thread": not resume,
                    "usage_baseline": read_feed(
                        run_dir / "activity-events.jsonl", tail=True
                    )["usage_baseline"],
                    "status": "running",
                    "ended_at": None,
                }
                _json(attempts / (attempt_id + ".json"), activity_attempt)
                record["activity_attempt_id"] = attempt_id
                record.update(evidence_complete="unknown", completion_basis=None)
                self.cancel_flags[run_id] = cancelled
                record["status"] = "running"
                record["snapshot_ready"] = False
                record["post_run_hash"] = None
                record["output_ref"] = None
                record["controller_cleanup"] = "not_started"
                record["attempt_finished"] = False
                name = "laomedo-codex-" + uuid4().hex
                launch_token = uuid4().hex
                record["container_ownership"] = {
                    "name": name,
                    "docker_endpoint": (self.docker_environment or {}).get(
                        "DOCKER_HOST"
                    ),
                    "launch_token": launch_token,
                    "supervised": self.supervise_containers,
                    "cleanup_verified": False,
                }
                _json(run_dir / "record.json", record)
            try:
                verify(
                    run_dir / "workspace",
                    record["skills"],
                    record.get("skill_git_exclusion", {"enabled": False}),
                )
            except ValueError as exc:
                raise RunnerError(str(exc)) from None
            if self.supervise_containers:
                if self.lease_service is None:
                    raise RunnerError("lease_service_required")
                try:
                    lease = LeaseClient(
                        self.lease_service,
                        run_id=run_id,
                        name=name,
                        docker_endpoint=(self.docker_environment or {}).get(
                            "DOCKER_HOST"
                        ),
                        token=launch_token,
                        cancelled=cancelled,
                        mediation_request=record.get("github_scope"),
                    )
                except (OSError, RuntimeError):
                    raise RunnerError("lease_service_unavailable") from None
                record["container_ownership"]["lease_instance"] = lease.instance
                record["container_ownership"]["grant_id"] = lease.grant_id
                if self.publication_controller is not None and record.get(
                    "github_scope"
                ):
                    self.publication_controller.register(lease, record)
                with self.control_lock:
                    _json(run_dir / "record.json", record)
            capability = None
            mediator_url = None
            mediator_instance = None
            if record.get("github_scope") is not None:
                if lease is None or lease.grant_id is None:
                    raise RunnerError("mediated_grant_unavailable")
                capability = lease.dir / "grant.secret"
                if capability.is_symlink() or not capability.is_file():
                    raise RunnerError("mediated_capability_unavailable")
                mediator_url, mediator_instance = self._mediator_route()
            access_token, auth_summary = (
                self.auth.access_token() if self.auth else (None, None)
            )
            if resume and self.auth:
                prior = record.get("credential") or {}
                if any(
                    auth_summary.get(key) != prior.get(key)
                    for key in ("credential_ref", "provider_subject_hash")
                ):
                    raise RunnerError("resume_auth_identity_mismatch")
            record["credential"] = auth_summary
            _json(run_dir / "record.json", record)
            transport_settings = Settings.load()
            launch_attempted = True
            server = self._open_server(
                run_dir,
                lifetime_seconds=(
                    NATIVE_TURN_SECONDS * (1 + record.get("output_retries", 0))
                    + transport_settings.startup_margin
                ),
                access_token=access_token,
                name=name,
                run_id=run_id,
                launch_token=launch_token,
                capability=capability,
                mediator_url=mediator_url,
                mediator_instance=mediator_instance,
                repository=(record.get("github_scope") or {}).get("repository"),
                branch=(record.get("github_scope") or {}).get("branch"),
                base_branch=(record.get("github_scope") or {}).get(
                    "base_branch", "main"
                ),
            )
            record["controller_cleanup"] = "pending"
            # Keep the pre-launch name/launch-token/grant ownership binding;
            # lifecycle diagnostics must not replace it with a name-only map.
            _json(run_dir / "record.json", record)
            await server.initialize()
            entries = await server.models()
            choice = next(
                (x for x in entries if x["id"] == record["requested_model"]), None
            )
            levels = set((choice or {}).get("efforts", []))
            if choice is None or record["requested_effort"] not in levels:
                raise RunnerError("unsupported_model_effort")
            if cancelled.is_set():
                record.update(
                    status="cancelled",
                    error_category="cancelled_before_turn",
                    cancel_requested=True,
                )
                return record
            self._turn_available()
            native_id = await server.open(record, resume=resume)
            record["thread_id"] = native_id
            record["precheck"]["installed"] = bool(record.get("output_requirements"))
            record["effective_model"] = record["requested_model"]
            record["effective_effort"] = record["requested_effort"]
            # ACP echoes adapter configuration, not an independent native report.
            record["effective_model_source"] = "host_requested_adapter_asserted"
            record["effective_effort_source"] = "host_requested_adapter_asserted"
            _json(run_dir / "record.json", record)
            if cancelled.is_set():
                record.update(
                    status="cancelled",
                    error_category="cancelled_before_turn",
                    cancel_requested=True,
                )
                return record
            attempt = self._reserve_turn()
            record["attempt_number"] = attempt
            _json(run_dir / "record.json", record)
            if cancelled.is_set():
                record.update(
                    status="cancelled",
                    error_category="cancelled_before_turn",
                    cancel_requested=True,
                )
                return record
            if record.get("github_scope") is not None:
                task += (
                    "\n\nThis run has approved, bounded GitHub mediation "
                    "for its selected Actions reads, bound PR read/create/update, and "
                    "verified-commit branch push operations. A "
                    "bundle_freeze request only captures the fixed in-run "
                    "Git bundle; it does not verify or push it. "
                    "To request one of those operations, pipe one JSON object "
                    "with repository, operation, payload and (for a write) "
                    "effect_id to `node /run/laomedo/mediate.mjs`. "
                    "The client reads its run capability from a read-only file; "
                    "never print or copy that file. A denied or unknown write "
                    "must not be retried automatically. Direct host GitHub "
                    "credentials and ambient gh login are unavailable."
                )
                if self.git_workspace:
                    task += (
                        " Native `git push origin HEAD:refs/heads/"
                        + record["github_scope"]["branch"]
                        + "` and `git fetch origin` use the mediated helper. "
                        "Fetch requires an explicitly granted read operation. "
                        "The supported `gh pr view/create/edit`, `gh run list`, "
                        "and GET-only `gh api` adapter is on PATH. "
                        "PR writes require LAOMEDO_EFFECT_ID and "
                        "LAOMEDO_RECONCILIATION_MARKER, an explicit title/body "
                        "and target; unsupported commands fail visibly. "
                        "Updates require a fast-forward from this run's "
                        "last confirmed push; never force or fall back "
                        "to direct HTTPS."
                    )
            turn_text = task
            if record.get("output_requirements"):
                turn_text += (
                    "\nReturn your final submission as a JSON object with explicit task_outcome "
                    "success or failure. Use laomedo_output_precheck on your form before "
                    "handoff and correct rejected fields within this request. Requirements: "
                    + json.dumps(record["output_requirements"], sort_keys=True)
                )
            server.assert_controller_isolated()
            if self.auth:
                auth_failure = {
                    "error": "auth_revoked_during_turn",
                    "outcome": "revoked",
                    "code": "auth_revoked",
                }

                def still_authorized():
                    try:
                        current = self.auth.active()
                        selected = self.auth.summary(current)
                    except AuthError as exc:
                        category, outcome = _auth_record_error(exc)
                        auth_failure.update(
                            error=category + "_during_turn",
                            outcome=outcome,
                            code=str(exc),
                        )
                        return False
                    except (OSError, ValueError):
                        auth_failure.update(
                            error="auth_unavailable_during_turn",
                            outcome="unavailable",
                            code="auth_mode_unavailable",
                        )
                        return False
                    if current.get("state") != "active":
                        if current.get("state") in {
                            "refresh_unknown",
                            "refresh_in_flight",
                        }:
                            auth_failure.update(
                                error="auth_refresh_failed_during_turn",
                                outcome="refresh_unknown",
                                code="auth_refresh_unknown",
                            )
                        return False
                    if any(
                        selected.get(key) != auth_summary.get(key)
                        for key in ("credential_ref", "provider_subject_hash")
                    ):
                        auth_failure.update(
                            error="auth_account_changed_during_turn",
                            outcome="account_mismatch",
                            code="auth_account_mismatch",
                        )
                        return False
                    if selected.get("generation") != auth_summary.get("generation"):
                        auth_failure.update(
                            error="auth_generation_changed_during_turn",
                            outcome="generation_changed",
                            code="auth_generation_changed",
                        )
                        return False
                    return True

                server.authorization_probe = still_authorized
                if not still_authorized():
                    raise AuthError(auth_failure["code"])
            turn_event_offset = len(server.events)
            native = await server.prompt(
                turn_text,
                skills=record["skills"],
                seconds=NATIVE_TURN_SECONDS,
                cancelled=cancelled,
            )
            turn_id, status, error = native.turn_id, native.status, native.error
            # Correction is a continuation of this native thread, never a new
            # dispatch of the original task. Any mediated scope or tool effect
            # blocks automatic continuation because safe repetition is unknown.
            correction_count = 0
            while record.get("output_requirements") and status == "completed":
                try:
                    submission = json.loads(
                        _answer(server.events[turn_event_offset:]) or "null"
                    )
                except (ValueError, TypeError):
                    submission = None
                validation = evaluate(record["output_requirements"], submission)
                record["output_validation"] = validation
                if (
                    validation["contract_status"] == "accepted"
                    or isinstance(submission, dict)
                    and submission.get("task_outcome") == "failure"
                    or correction_count >= record["output_retries"]
                ):
                    break
                commands_before = _command_summary(server.events, turn_id)

                def effect_event(event):
                    if event.get("method") not in {"item/started", "item/completed"}:
                        return False
                    item = event.get("params", {}).get("item") or {}
                    if item.get("type") in {"userMessage", "agentMessage", "reasoning"}:
                        return False
                    return not (
                        item.get("type") == "dynamicToolCall"
                        and item.get("tool") == "laomedo_output_precheck"
                        and item.get("namespace") is None
                        and item.get("id")
                        in getattr(server, "verified_precheck_calls", set())
                    )

                tool_effect = any(effect_event(event) for event in server.events)
                if (
                    record.get("github_scope")
                    or tool_effect
                    or commands_before["commands"]
                    or commands_before["identity_incomplete"]
                ):
                    record["output_correction_blocked"] = (
                        "side_effect_safety_unverified"
                    )
                    break
                if cancelled.is_set():
                    status, error = "cancelled", "cancelled_by_user"
                    break
                attempt = self._reserve_turn()
                record["turns"].append(
                    {
                        "turn_id": turn_id,
                        "status": status,
                        "correction_pending": True,
                        "output_validation": validation,
                    }
                )
                correction_count += 1
                record["attempt_number"] = attempt
                record["output_correction_count"] = correction_count
                _json(run_dir / "record.json", record)
                feedback = (
                    "Continue this same session by correcting only your output form. "
                    "Do not repeat the original task or any external writes. "
                    "Use the existing output precheck. Validation feedback: "
                    + json.dumps(validation, sort_keys=True)
                )
                server.assert_controller_isolated()
                if self.auth and not still_authorized():
                    raise AuthError(auth_failure["code"])
                turn_event_offset = len(server.events)
                native = await server.prompt(
                    feedback,
                    skills=record["skills"],
                    seconds=NATIVE_TURN_SECONDS,
                    cancelled=cancelled,
                )
                turn_id, status, error = native.turn_id, native.status, native.error
            native_status = status
            commands = _command_summary(server.events, turn_id)
            record["native_turn_status"] = native_status
            record["precheck"]["call_count"] = getattr(server, "precheck_call_count", 0)
            record["command_summary"] = commands
            record["native_answer"] = (
                _answer(server.events[turn_event_offset:])
                if native_status == "completed"
                else None
            )
            if status == "completed" and (
                commands["outstanding_ids"] or commands["identity_incomplete"]
            ):
                status, error = "unknown", "outstanding_command_completion_unknown"
            if self.auth and error == "auth_revoked_during_turn":
                error = auth_failure["error"]
                record["credential"]["auth_outcome"] = auth_failure["outcome"]
            native_errors = _native_error_summary(server.events, turn_id)
            if status == "failed" and error is None and native_errors["last_category"]:
                error = "codex_" + native_errors["last_category"]
            record["turns"].append(
                {
                    "turn_id": turn_id,
                    "status": status,
                    "native_turn_status": native_status,
                    "command_summary": commands,
                    "error_category": error,
                    "native_completion_status": getattr(
                        server, "native_completion_status", None
                    ),
                    "interrupt_acknowledged": getattr(
                        server, "interrupt_acknowledged", False
                    ),
                    "native_error_summary": native_errors,
                    "input_hash": "sha256:" + hashlib.sha256(task.encode()).hexdigest(),
                }
            )
            record["status"] = "completed" if status == "completed" else status
            record["error_category"] = error
            if status == "cancelled":
                record["cancel_requested"] = True
            record["native_error_summary"] = native_errors
            record["answer"] = (
                _answer(server.events[turn_event_offset:])
                if status == "completed"
                else None
            )
            if status == "completed" and not record["answer"]:
                raise RunnerError("completed_without_agent_message")
            self._verify_protected_mounts(run_dir, record)
            if lease is not None and lease.lost.is_set():
                raise RunnerError("lease_service_lost")
        except Exception as exc:
            if record is None:
                raise
            if record["status"] not in {"interrupted", "cancelled"}:
                record["status"] = "failed"
                if isinstance(exc, AuthError):
                    category, outcome = _auth_record_error(exc)
                    record["error_category"] = category
                    if isinstance(record.get("credential"), dict):
                        record["credential"]["auth_outcome"] = outcome
                else:
                    record["error_category"] = (
                        str(exc) if isinstance(exc, RunnerError) else type(exc).__name__
                    )
        finally:
            close_error = False
            try:
                if server is not None:
                    if record is not None:
                        count = getattr(server, "precheck_call_count", 0)
                        record["precheck"]["call_count"] = count
                        record["precheck"]["installed"] = record["precheck"][
                            "installed"
                        ] or bool(getattr(server, "verified_precheck_calls", set()))
                    await server.close()
                    if record is not None:
                        record["controller_cleanup"] = "confirmed"
                        if not self.supervise_containers and getattr(
                            server, "cleanup_confirmed", False
                        ):
                            record["container_ownership"].update(
                                cleanup_verified=True, cleanup_detail="removed"
                            )
                    if record is not None and record.get("status") == "cancelled":
                        record["cancel_confirmed"] = True
            except Exception as close_failure:
                close_error = True
                if record is not None:
                    record.update(
                        status="failed",
                        error_category=(
                            close_failure.code
                            if isinstance(close_failure, RunnerError)
                            and close_failure.code
                            in {
                                "executor_termination_unverified",
                                "container_termination_unverified",
                                "runner_transport_failed",
                            }
                            else "container_termination_unverified"
                        ),
                    )
                    record["controller_cleanup"] = "unverified"
            else:
                if record is not None and record.get("status") == "completed":
                    try:
                        record["post_run_hash"] = self._freeze_workspace(
                            run_dir, record
                        )
                        record["output_ref"] = f"laomedo:run:{run_id}:workspace"
                        record["snapshot_ready"] = True
                    except Exception as snapshot_failure:
                        record.update(
                            status="failed",
                            answer=None,
                            error_category=(
                                snapshot_failure.code
                                if isinstance(snapshot_failure, RunnerError)
                                else "workspace_copy_mismatch"
                            ),
                        )
            finally:
                try:
                    if (
                        record is not None
                        and record.get("status") != "completed"
                        and self.publication_controller is not None
                    ):
                        self.publication_controller.cancel(run_id, "failed")
                    if (
                        record is not None
                        and self.supervise_containers
                        and not launch_attempted
                    ):
                        verified, detail = True, "not_launched"
                        if lease is not None:
                            try:
                                lease.finish()
                            except Exception:
                                verified, detail = False, "lease_service_unverified"
                        record["container_ownership"]["cleanup_verified"] = verified
                        record["container_ownership"]["cleanup_detail"] = detail
                        if not verified:
                            record.update(
                                status="failed",
                                error_category="container_termination_unverified",
                            )
                    elif record is not None and self.supervise_containers:
                        verified, detail = (
                            (True, "removed")
                            if getattr(server, "cleanup_confirmed", False)
                            else cleanup_exact(
                                ContainerIdentity(
                                    name=name,
                                    run_id=run_id,
                                    token=launch_token,
                                    docker_endpoint=(self.docker_environment or {}).get(
                                        "DOCKER_HOST"
                                    ),
                                )
                            )
                        )
                        if lease is not None:
                            # The executor is already removed. Only a trusted
                            # controller can keep its SAME lease through output
                            # validation; no graph bearer can extend it.
                            record["container_ownership"]["cleanup_verified"] = verified
                            record["container_ownership"]["cleanup_detail"] = detail
                            record.update(
                                _execution_evidence(
                                    run_dir / "raw-events.jsonl",
                                    evidence_offset,
                                    record,
                                    record["turns"][attempt_turn_offset:],
                                    resumed=resume,
                                    streams_closed=(
                                        server is not None and (server.streams_closed)
                                    ),
                                )
                            )
                            retained = (
                                verified
                                and not close_error
                                and self.publication_controller is not None
                                and self.publication_controller.finish_agent(record)
                            )
                            if not retained:
                                try:
                                    lease.finish()
                                except Exception:
                                    verified = False
                                    detail = "lease_service_unverified"
                        record["container_ownership"]["cleanup_verified"] = verified
                        record["container_ownership"]["cleanup_detail"] = detail
                        if not verified:
                            record.update(
                                status="failed",
                                error_category="container_termination_unverified",
                            )
                    with self.control_lock:
                        if record is not None:
                            record["attempt_finished"] = True
                            if record.get("status") != "completed":
                                record.update(
                                    evidence_complete="unknown", completion_basis=None
                                )
                            if record.get("status") != "completed":
                                record["snapshot_ready"] = False
                                record["post_run_hash"] = None
                                record["output_ref"] = None
                            if cancelled is not None and cancelled.is_set():
                                record["cancel_requested"] = True
                            if activity_attempt is not None:
                                from laomedo.agents.activity.utils import now

                                try:
                                    activity_attempt.update(
                                        native_end=line_count(
                                            run_dir / "activity-events.jsonl"
                                        ),
                                        otel_end=line_count(
                                            run_dir / "otel-events.jsonl"
                                        ),
                                        status=record["status"],
                                        ended_at=now(),
                                    )
                                    _json(
                                        run_dir
                                        / "activity-attempts"
                                        / (activity_attempt["id"] + ".json"),
                                        activity_attempt,
                                    )
                                except OSError:
                                    pass  # An observation failure cannot change execution success.
                            _json(run_dir / "record.json", record)
                        self.cancel_flags.pop(run_id, None)
                finally:
                    self.lock.release()
        return record
