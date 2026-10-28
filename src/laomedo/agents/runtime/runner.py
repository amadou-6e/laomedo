"""Single-user local Codex runner backed by the tested Docker profile."""

from __future__ import annotations

from pathlib import Path
from urllib.request import urlopen
from uuid import uuid4
import hashlib
import json
import laomedo.agents.artifacts.errors as _artifacts_errors
import laomedo.agents.artifacts.utils as _artifacts_utils
import laomedo.agents.contracts.output as _contracts_output
import laomedo.agents.runtime.settings as _runtime_settings
import laomedo.agents.runtime.errors as _runtime_errors
import laomedo.agents.runtime.servers as _runtime_servers
import laomedo.agents.runtime.utils as _runtime_utils
import laomedo.agents.workspace.errors as _agents_workspace_errors
import laomedo.agents.workspace.git as _workspace_git
import laomedo.host.credentials.siwc.connection as _siwc_connection
import laomedo.host.credentials.siwc.errors as _siwc_errors
import laomedo.host.credentials.siwc.utils as _siwc_utils
import laomedo.host.leases.client as _leases_client
import laomedo.host.leases.models as _leases_models
import laomedo.host.leases.utils as _leases_utils
import laomedo.host.mediation.authority as _mediation_authority
import laomedo.host.mediation.errors as _mediation_errors
import laomedo.skills.registry.store as _registry_store
import laomedo.skills.registry.utils as _registry_utils
import laomedo.skills.workspace.errors as _skills_workspace_errors
import laomedo.skills.workspace.utils as workspace_skills
import os
import laomedo.host.credentials.claude.settings as _host_claude_settings
import re
import secrets
import shutil
import subprocess
import threading
import time


class LocalRunner:
    def __init__(
        self,
        state: Path,
        skill_store: Path,
        source_workspace: Path,
        *,
        transport=_runtime_servers.AppServer,
        check_docker: bool = True,
        supervise_containers: bool | None = None,
        lease_service: Path | None = None,
        github_authority: _mediation_authority.RunGrantAuthority | None = None,
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
        self.state = _runtime_utils._private(state)
        self.store = _registry_store.SkillStore(skill_store)
        self.source = source_workspace.expanduser().resolve()
        self.git_workspace = git_workspace
        self.image = (
            _runtime_settings.GIT_IMAGE if git_workspace else _runtime_settings.IMAGE
        )
        self.image_id = (
            _runtime_settings.GIT_IMAGE_ID
            if git_workspace
            else _runtime_settings.IMAGE_ID
        )
        if image_id is not None:
            if (
                git_workspace
                or split_executor
                or not isinstance(image_id, str)
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id)
            ):
                raise _runtime_errors.RunnerError("invalid_local_image_id")
            # Trusted host startup configuration, never a per-run API input.
            self.image_id = image_id
        if (
            not self.source.is_dir()
            or (self.source / ".git").is_dir() != git_workspace
            or (not git_workspace and not _runtime_utils._git_tree(self.source))
        ):
            raise _runtime_errors.RunnerError("source_workspace_must_be_git_tree")
        if self.state == self.store.root or self.state.is_relative_to(self.store.root):
            raise _runtime_errors.RunnerError("state_overlaps_skill_store")
        self.state.mkdir(parents=True, exist_ok=True)
        token_path = self.state / "api-token"
        try:
            fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as token_file:
                token_file.write(secrets.token_hex(32))
        self.api_token = token_path.read_text(encoding="utf-8")
        if not re.fullmatch(r"[0-9a-f]{64}", self.api_token):
            raise _runtime_errors.RunnerError("invalid_runner_api_token")
        (self.state / "runs").mkdir(exist_ok=True)
        self.supervise_containers = (
            transport is _runtime_servers.AppServer and not split_executor
            if supervise_containers is None
            else supervise_containers
        )
        if split_executor and self.supervise_containers:
            raise _runtime_errors.RunnerError("split_executor_lease_unavailable")
        if git_workspace and split_executor:
            raise _runtime_errors.RunnerError("git_workspace_split_unsupported")
        # The lease service is started independently of this runner, so a
        # whole-process-tree kill of the runner cannot also kill it.
        self.lease_service = Path(lease_service).resolve() if lease_service else None
        self.artifact_sources = {}
        for provider, source_state in (artifact_sources or {}).items():
            if provider not in {"codex", "opencode", "claude"}:
                raise _runtime_errors.RunnerError("invalid_artifact_provider")
            self.artifact_sources[provider] = _runtime_utils._private(
                Path(source_state)
            )
        self.publication_controller = publication_controller
        self.github_authority = github_authority
        self.mediator_state = (
            _runtime_utils._private(mediator_state) if mediator_state else None
        )
        for record_path in (self.state / "runs").glob("*/record.json"):
            record = _runtime_utils._read(record_path)
            if record.get("status") in {"prepared", "running"}:
                record["status"] = "interrupted"
                record["error_category"] = "runner_restarted"
                owner = record.get("container_ownership") or {}
                if owner.get("supervised"):
                    verified, detail = _leases_utils.cleanup_exact(
                        _leases_models.ContainerIdentity(
                            name=owner["name"],
                            run_id=record["run_id"],
                            token=owner["launch_token"],
                        )
                    )
                    owner["cleanup_verified"] = verified
                    owner["cleanup_detail"] = detail
                    if not verified:
                        record["error_category"] = "container_cleanup_unverified"
                _runtime_utils._json(record_path, record)
        self.transport = transport
        self.split_executor = split_executor
        self.split_provider_config = tuple(split_provider_config)
        self.split_access_token = split_access_token
        if auth_store is not None and not split_executor:
            raise _runtime_errors.RunnerError("app_owned_auth_requires_split_executor")
        if auth_store is not None and (split_provider_config or split_access_token):
            raise _runtime_errors.RunnerError("conflicting_split_auth_sources")
        if auth_store is not None:
            auth_root = _siwc_utils._outside_git(auth_store)
            if (
                auth_root == self.state
                or auth_root.is_relative_to(self.state)
                or self.state.is_relative_to(auth_root)
                or auth_root == self.store.root
                or auth_root.is_relative_to(self.store.root)
                or self.store.root.is_relative_to(auth_root)
            ):
                raise _runtime_errors.RunnerError("auth_store_overlaps_runner_state")
            self.auth = _siwc_connection.ChatGPTConnection(auth_root)
        else:
            self.auth = None
        self.instance_id = str(uuid4())
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
        self.profile = (
            _runtime_utils._split_profile(self.state)
            if split_executor
            else _runtime_settings.VOLUME
        )
        if split_executor and transport is not _runtime_servers.AppServer:
            raise _runtime_errors.RunnerError(
                "split_executor_requires_native_transport"
            )
        if (
            self.split_provider_config or split_access_token is not None
        ) and not split_executor:
            raise _runtime_errors.RunnerError("split_provider_requires_split_executor")
        self.lock = threading.Lock()
        self.control_lock = threading.Lock()
        self.request_lock = threading.Lock()
        self.cancel_flags = {}
        # The checked-in policy is LF on Linux and CRLF in Windows worktrees.
        # Accept only these two reviewed byte representations of the same policy.
        if hashlib.sha256(_runtime_settings.CONFIG.read_bytes()).hexdigest() not in {
            _runtime_settings.CONFIG_SHA256,
            _runtime_settings.CONFIG_LF_SHA256,
        }:
            raise _runtime_errors.RunnerError("permission_config_changed")
        if check_docker:
            found = subprocess.run(
                ["docker", "image", "inspect", self.image, "--format", "{{.Id}}"],
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            )
            if found.stdout.strip() != self.image_id:
                raise _runtime_errors.RunnerError("docker_image_digest_changed")
            version = subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--pull=never",
                    "--network",
                    "none",
                    "--cap-drop",
                    "ALL",
                    "--security-opt",
                    "no-new-privileges",
                    "--user",
                    "10001:10001",
                    self.image_id,
                    "codex",
                    "--version",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
            )
            if version.stdout.strip() != _runtime_settings.CLI_VERSION:
                raise _runtime_errors.RunnerError("unsupported_codex_cli_version")
            if not split_executor:
                subprocess.run(
                    ["docker", "volume", "inspect", _runtime_settings.VOLUME],
                    check=True,
                    capture_output=True,
                    timeout=15,
                )
            else:
                _runtime_utils._ensure_split_profile(self.profile)

    def _open_server(
        self,
        root: Path,
        *,
        access_token=None,
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
        if self.split_executor:
            return _runtime_servers.SplitAppServer(
                workspace,
                canonical,
                store_mount,
                root,
                self.profile,
                provider_config=self.split_provider_config,
                access_token=(
                    access_token
                    if access_token is not None
                    else self.split_access_token
                ),
            )
        command_directory = None
        if capability is not None and self.git_workspace:
            import laomedo.host.mediation.agent_cli as _mediation_agent_cli

            if repository is None or branch is None:
                raise _runtime_errors.RunnerError("mediated_command_scope_missing")
            command_directory = _mediation_agent_cli.prepare_commands(
                root, repository, branch
            )
            # The checkout was prepared without a provider remote. This is a
            # credential-free helper URL, not an HTTPS fallback.
            _mediation_agent_cli.configure_remote(workspace, repository)
        # Launch the opt-in image by its verified ID, not a mutable local tag.
        command = [
            "docker",
            *_runtime_utils._docker_prefix(
                workspace,
                canonical,
                store_mount,
                image=self.image_id,
                name=name,
                run_id=run_id,
                launch_token=launch_token,
                capability=capability,
                mediator_url=mediator_url,
                mediator_instance=mediator_instance,
                command_directory=command_directory,
                repository=repository,
                branch=branch,
                base_branch=base_branch,
            ),
        ]
        if capability is not None and self.transport is _runtime_servers.AppServer:
            return self.transport(
                command,
                root,
                secret_redactions=(capability.read_text(encoding="utf-8").strip(),),
            )
        return self.transport(command, root)

    def model_catalog(self) -> dict:
        """Serialize and briefly cache metadata discovery; never submit a turn."""
        # Lazy initialization also supports existing host-created runner objects.
        with _runtime_settings._CATALOG_INIT_LOCK:
            if not hasattr(self, "_catalog_lock"):
                self._catalog_lock = threading.Lock()
                self._catalog_cached = None
        with self._catalog_lock:
            cached = self._catalog_cached
            if cached and time.monotonic() - cached[0] < 30:
                return cached[1]
            root = self.state / "catalog" / str(uuid4())
            server = None
            try:
                for name in ("workspace", "canonical", "store"):
                    (root / name).mkdir(parents=True)
                # Deliberately use runner authentication when configured: metadata
                # may be account-specific. No thread or turn is requested.
                token = self.auth.access_token()[0] if self.auth else None
                server = self._open_server(root, access_token=token)
                initialized = server.request(
                    "initialize",
                    {
                        "clientInfo": {
                            "name": "laomedo_model_catalog",
                            "version": "0.1.0",
                        },
                        **(
                            {"capabilities": {"experimentalApi": True}}
                            if self.split_executor
                            else {}
                        ),
                    },
                )
                if "result" not in initialized:
                    raise _runtime_errors.RunnerError("initialize_rejected")
                server.notify("initialized", {})
                result = {
                    "models": _runtime_utils._advertised_models(server),
                    "submitted_turns": 0,
                }
                self._catalog_cached = (time.monotonic(), result)
                return result
            finally:
                try:
                    if server is not None:
                        server.close()
                finally:
                    shutil.rmtree(root, ignore_errors=True)

    def preflight(self) -> dict:
        """Check the existing Docker app-server and advertised models without a turn."""
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
            server = self._open_server(root, access_token=token)
            initialized = server.request(
                "initialize",
                {
                    "clientInfo": {
                        "name": "laomedo_local_runner",
                        "title": "Laomedo Local Runner",
                        "version": "0.1.0",
                    },
                    **(
                        {"capabilities": {"experimentalApi": True}}
                        if self.split_executor
                        else {}
                    ),
                },
            )
            if "result" not in initialized:
                raise _runtime_errors.RunnerError("initialize_rejected")
            server.notify("initialized", {})
            if self.split_executor:
                server.register_executor()
            models = _runtime_utils._advertised_models(server)
            checks = {}
            if self.split_executor:
                # Direct checks against the tool executor. Calling command/exec
                # on app-server would execute inside the credential controller.
                for label, command in (
                    ("workspace_write", "printf CANARY > /draft/canary.txt"),
                    ("canonical_write", "printf FORBIDDEN > /canonical/sentinel.txt"),
                    ("store_write", "printf FORBIDDEN > /store/sentinel.txt"),
                    ("auth_read", "cat /home/runner/.codex/auth.json >/dev/null"),
                ):
                    response = subprocess.run(
                        ["docker", "exec", server.executor_name, "sh", "-c", command],
                        capture_output=True,
                        timeout=15,
                    )
                    checks[label] = response.returncode
            else:
                for label, command in (
                    ("workspace_write", "printf CANARY > /draft/canary.txt"),
                    ("canonical_write", "printf FORBIDDEN > /canonical/sentinel.txt"),
                    ("store_write", "printf FORBIDDEN > /store/sentinel.txt"),
                    ("auth_read", "cat /home/runner/.codex/auth.json >/dev/null"),
                ):
                    response = server.request(
                        "command/exec",
                        {
                            "command": ["sh", "-c", command],
                            "cwd": "/draft",
                            "timeoutMs": 15000,
                        },
                        timeout=25,
                    )
                    checks[label] = (response.get("result") or {}).get("exitCode")
            if self.git_workspace:
                git_check = server.request(
                    "command/exec",
                    {
                        "command": ["git", "--version"],
                        "cwd": "/draft",
                        "timeoutMs": 15000,
                    },
                    timeout=25,
                )
                checks["git_binary"] = (git_check.get("result") or {}).get("exitCode")
                if checks["git_binary"] != 0:
                    raise _runtime_errors.RunnerError("git_image_missing_git")
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
                raise _runtime_errors.RunnerError("permission_preflight_failed")
            return {
                "status": "ready",
                "models": models,
                "image": self.image,
                "image_id": self.image_id,
                "cli_version": _runtime_settings.CLI_VERSION,
                "profile": self.profile,
                "config_sha256": _runtime_settings.CONFIG_SHA256,
                "permission_checks": checks,
                "submitted_turns": 0,
            }
        finally:
            if server is not None:
                server.close()

    def _run_dir(self, run_id: str) -> Path:
        return self.state / "runs" / _runtime_utils._id(run_id)

    def _reserve_turn(self) -> int:
        # Diagnostic sequence only; neither corrupt accounting nor a write failure
        # may become an authorization gate. Historical turn-ledger.json is untouched.
        ledger = self.state / "attempt-count.json"
        count = getattr(self, "_observed_turns", 0)
        try:
            value = _runtime_utils._read(ledger) if ledger.exists() else {}
            saved = value.get("attempted_turns")
        except (OSError, ValueError, TypeError, AttributeError):
            saved = None
        if type(saved) is int and saved >= 0:
            count = max(count, saved)
        else:
            for path in (self.state / "runs").glob("*/record.json"):
                try:
                    prior = _runtime_utils._read(path).get("attempt_number", 0)
                    if type(prior) is int and prior >= 0:
                        count = max(count, prior)
                except (OSError, ValueError, TypeError, AttributeError):
                    continue
        self._observed_turns = count + 1
        try:
            _runtime_utils._json(ledger, {"attempted_turns": count + 1})
        except OSError:
            pass
        return count + 1

    def _turn_available(self) -> None:
        """Extension point for isolated experiment harnesses; no production quota."""

    def status(self, run_id: str) -> dict:
        return _runtime_utils._read(self._run_dir(run_id) / "record.json")

    def lookup_request(self, request_id: str) -> dict:
        """Find one durable async run without starting or changing it."""
        try:
            _runtime_utils._id(request_id)
        except (TypeError, ValueError, AttributeError):
            raise _runtime_errors.RunnerError("invalid_request_id") from None
        with self.request_lock:
            matches = []
            for record_path in (self.state / "runs").glob("*/record.json"):
                record = _runtime_utils._read(record_path)
                if record.get("client_request_id") == request_id:
                    matches.append(record)
            if not matches:
                raise _runtime_errors.RunnerError("request_not_found")
            if len(matches) != 1:
                raise _runtime_errors.RunnerError("request_identity_conflict")
            record = matches[0]
            return {
                key: record.get(key)
                for key in (
                    "client_request_id",
                    "request_hash",
                    "run_id",
                    "provider",
                    "raw_event_ref",
                    "status",
                )
            }

    def cancel(self, run_id: str) -> dict:
        if self.publication_controller is not None:
            self.publication_controller.cancel(run_id)
        with self.control_lock:
            record = self.status(run_id)
            if record["status"] == "prepared" and record.get("client_request_id"):
                record.update(
                    status="cancelled",
                    error_category="cancelled_before_dispatch",
                    cancel_requested=True,
                    cancel_confirmed=True,
                )
                _runtime_utils._json(self._run_dir(run_id) / "record.json", record)
                return record
            if record["status"] == "running":
                flag = self.cancel_flags.get(run_id)
                if flag is None:
                    raise _runtime_errors.RunnerError("run_not_active_in_this_process")
                flag.set()
                record.update(cancel_requested=True, cancel_confirmed=False)
                _runtime_utils._json(self._run_dir(run_id) / "record.json", record)
                return record
            return record

    def publish(self, run_id: str) -> dict:
        if self.publication_controller is None:
            raise _runtime_errors.RunnerError("publication_controller_unconfigured")
        try:
            result = self.publication_controller.publish(run_id)
        except _mediation_errors.MediationError as error:
            raise _runtime_errors.RunnerError(error.code) from None
        return {
            "status": "completed" if result["phase"] == "completed" else "failed",
            "run_id": run_id,
            "publication_handoff": result,
        }

    def _materialize(self, workspace: Path, ref: dict) -> dict:
        if not isinstance(ref, dict) or not all(
            ref.get(k) for k in ("skill_id", "revision_id", "tree_hash")
        ):
            raise _runtime_errors.RunnerError("pinned_skill_ref_required")
        if ref["revision_id"] != ref["tree_hash"]:
            raise _runtime_errors.RunnerError("skill_ref_hash_mismatch")
        record = self.store.revision(ref["skill_id"], ref["revision_id"])
        if record["tree_hash"] != ref["tree_hash"]:
            raise _runtime_errors.RunnerError("skill_ref_hash_mismatch")
        target = workspace / ".agents" / "skills" / ref["skill_id"]
        if target.exists():
            raise _runtime_errors.RunnerError("skill_path_conflict")
        target.mkdir(parents=True)
        for relative, expected in record["file_hashes"].items():
            item = self.store.read_file(ref["skill_id"], ref["revision_id"], relative)
            if item["file_hash"] != expected:
                raise _runtime_errors.RunnerError("skill_file_hash_mismatch")
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(item["content"])
        if (
            _registry_utils.tree_hash(_registry_utils.inventory(target))
            != ref["tree_hash"]
        ):
            raise _runtime_errors.RunnerError("materialized_skill_mismatch")
        try:
            skill_text = (target / "SKILL.md").read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            raise _runtime_errors.RunnerError(
                "skill_frontmatter_name_required"
            ) from None
        if not skill_text.startswith("---\n") or "\n---\n" not in skill_text[4:]:
            raise _runtime_errors.RunnerError("skill_frontmatter_name_required")
        frontmatter = skill_text[4:].split("\n---\n", 1)[0]
        names = [
            line.split(":", 1)[1].strip().strip("\"'")
            for line in frontmatter.splitlines()
            if line.startswith("name:")
        ]
        if names != [ref["skill_id"]]:
            raise _runtime_errors.RunnerError("skill_frontmatter_name_mismatch")
        return {
            "skill_id": ref["skill_id"],
            "revision_id": ref["revision_id"],
            "tree_hash": ref["tree_hash"],
            "file_hashes": record["file_hashes"],
            "delivery_mode": "project_discovery",
            "use_evidence": "offered",
        }

    def _prepare(
        self, request: dict, *, client_request_id=None, request_hash=None
    ) -> dict:
        if not isinstance(request, dict):
            raise _runtime_errors.RunnerError("invalid_request")
        task = request.get("task")
        if not isinstance(task, str) or not task.strip() or len(task) > 16000:
            raise _runtime_errors.RunnerError("invalid_task")
        model, effort = request.get("model"), request.get("effort")
        if not all(isinstance(x, str) and x for x in (model, effort)):
            raise _runtime_errors.RunnerError("model_and_effort_required")
        output_requirements = request.get("output_requirements")
        if output_requirements is not None:
            output_requirements = _contracts_output.verify_requirements(
                output_requirements
            )
        output_retries = request.get("output_retries", 1)
        if type(output_retries) is not int or not 0 <= output_retries <= 8:
            raise _runtime_errors.RunnerError("invalid_output_retry_count")
        if "skill_refs" in request and "skill_ref" in request:
            raise _runtime_errors.RunnerError("conflicting_skill_inputs")
        refs = (
            request["skill_refs"]
            if "skill_refs" in request
            else [request["skill_ref"]] if "skill_ref" in request else []
        )
        if not isinstance(refs, list) or len(refs) > 16:
            raise _runtime_errors.RunnerError("one_to_sixteen_skills_required")
        seen = set()
        for ref in refs:
            if not isinstance(ref, dict) or not isinstance(ref.get("skill_id"), str):
                raise _runtime_errors.RunnerError("pinned_skill_ref_required")
            if ref["skill_id"] in seen:
                raise _runtime_errors.RunnerError("duplicate_skill_id")
            seen.add(ref["skill_id"])
        source = self.source
        handoff = self._handoff(request.get("handoff"))
        if "github_scope" in request:
            raise _runtime_errors.RunnerError("github_scope_must_come_from_authority")
        github_ref = request.get("github_authorization_ref")
        if github_ref is not None and (
            self.github_authority is None
            or not self.supervise_containers
            or self.split_executor
            or self.lease_service is None
            or self.mediator_state is None
        ):
            raise _runtime_errors.RunnerError("mediated_lease_required")
        run_id = str(uuid4())
        run_dir = self._run_dir(run_id)
        run_dir.mkdir()
        workspace, canonical, store_mount = (
            run_dir / x for x in ("workspace", "canonical", "store")
        )
        try:
            try:
                github_scope = (
                    self.github_authority.bind_run(
                        github_ref,
                        run_id,
                        allowed_operations=frozenset(
                            {"actions_read", "pr_create", "pr_update", "pr_read"}
                            | (
                                {"git_push", "git_fetch"}
                                if self.git_workspace
                                else set()
                            )
                        ),
                    )
                    if github_ref is not None
                    else None
                )
            except _mediation_errors.MediationError as error:
                raise _runtime_errors.RunnerError(error.code) from None
            if self.git_workspace:
                try:
                    baseline = _workspace_git.prepare_git_workspace(source, workspace)
                except _agents_workspace_errors.GitWorkspaceError as error:
                    raise _runtime_errors.RunnerError(str(error)) from error
                source_hash = _runtime_utils._copy_tree(
                    workspace, canonical, exclude_root_git=True
                )
            else:
                baseline = None
                source_hash = _runtime_utils._copy_tree(source, workspace)
                # Preserve the tested read-only canonical and sibling store mounts.
                if _runtime_utils._copy_tree(source, canonical) != source_hash:
                    raise _runtime_errors.RunnerError("source_changed_during_snapshot")
            store_mount.mkdir()
            (store_mount / "sentinel.txt").write_text(
                "STORE-ORIGINAL", encoding="utf-8"
            )
            # prepare_git_workspace already created an isolated repository
            # with preserved history; do not replace it with a fresh baseline.
            if not self.git_workspace:
                workspace_skills.initialize(workspace)
            elif github_scope is not None:
                # Install trusted remote/handoff metadata before the immutable
                # skill exclusion digest. _open_server then verifies this same
                # remote and leaves the already-present rule unchanged.
                import laomedo.host.mediation.agent_cli as _mediation_agent_cli

                _mediation_agent_cli.configure_remote(
                    workspace, github_scope["repository"]
                )
            skills = [self._materialize(workspace, ref) for ref in refs]
            if not skills:
                try:
                    (workspace / ".agents" / "skills").mkdir(
                        parents=True, exist_ok=True
                    )
                except OSError:
                    raise _runtime_errors.RunnerError(
                        "unsafe_materialized_skill_path"
                    ) from None
            git_exclusion = workspace_skills.install(workspace, skills)
            if not skills:
                try:
                    workspace_skills.verify(workspace, skills, git_exclusion)
                except _skills_workspace_errors.WorkspaceSkillError as error:
                    raise _runtime_errors.RunnerError(str(error)) from None
            artifacts = _artifacts_utils.import_selected(
                request.get("artifact_refs", []),
                workspace,
                self._artifact_source,
                _runtime_utils._hash_tree,
            )
            effective_hash = _runtime_utils._hash_tree(
                workspace, exclude_root_git=self.git_workspace
            )
            (run_dir / "raw-events.jsonl").touch()
            record = {
                "schema_version": 1,
                "run_id": run_id,
                "status": "prepared",
                "error_category": None,
                "source_hash": source_hash,
                "workspace_mode": "git" if self.git_workspace else "files",
                "git_baseline": baseline,
                "post_run_hash_scope": (
                    "working_files_only" if self.git_workspace else "all_files"
                ),
                "effective_hash": effective_hash,
                "post_run_hash": None,
                "input_hash": "sha256:" + hashlib.sha256(task.encode()).hexdigest(),
                "skill": skills[0] if len(skills) == 1 else None,
                "skills": skills,
                "skill_git_exclusion": git_exclusion,
                "provider": getattr(self, "provider", "codex"),
                "handoff": handoff,
                "imported_artifacts": artifacts,
                "requested_model": model,
                "requested_effort": effort,
                "effective_model": None,
                "effective_effort": None,
                "profile": self.profile,
                "execution_mode": "split" if self.split_executor else "legacy",
                "image": self.image,
                "image_id": self.image_id,
                "cli_version": _runtime_settings.CLI_VERSION,
                "config_sha256": _runtime_settings.CONFIG_SHA256,
                "thread_id": None,
                "credential": (
                    {
                        "credential_mode": "chatgpt_plan_oauth",
                        "credential_ref": None,
                        "auth_outcome": "not_checked",
                    }
                    if self.auth
                    else None
                ),
                "runner_instance_id": self.instance_id,
                "turns": [],
                "answer": None,
                "output_ref": None,
                "raw_event_ref": f"laomedo:run:{run_id}:events",
                "client_request_id": client_request_id,
                "activity_initial_attempt_id": str(uuid4()),
                "output_requirements": output_requirements,
                "requirements_revision": (output_requirements or {}).get(
                    "requirements_revision"
                ),
                "output_retries": output_retries,
                "precheck": {"installed": False, "call_count": 0},
                "request_hash": request_hash,
                "cancel_requested": False,
                "cancel_confirmed": False,
            }
            if github_scope is not None:
                record["github_scope"] = github_scope
            _runtime_utils._json(run_dir / "record.json", record)
        except Exception:
            try:
                workspace_skills.remove_owned_tree(run_dir, self.state)
            except OSError:
                raise _runtime_errors.RunnerError(
                    "run_preparation_cleanup_unverified"
                ) from None
            raise
        return record

    def _mirror_host_login(self):
        if (
            getattr(self, "provider", None) == "claude"
            and _host_claude_settings.Settings().mirror_host_login == "1"
        ):
            import laomedo.host.credentials.claude.utils as _claude_utils
            import laomedo.host.credentials.claude.errors as _claude_errors

            try:
                _claude_utils.mirror_login(
                    self.container.profile, self.container.image_id
                )
            except _claude_errors.LocalClaudeLoginError as error:
                raise _runtime_errors.RunnerError(str(error)) from None

    def start(self, request: dict) -> dict:
        record = self._prepare(request)
        try:
            self._mirror_host_login()
        except _runtime_errors.RunnerError as exc:
            record.update(status="failed", error_category=str(exc))
            _runtime_utils._json(
                self._run_dir(record["run_id"]) / "record.json", record
            )
            raise
        return self._execute(record["run_id"], request["task"], resume=False)

    def start_async(self, request: dict, *, response_gate=None) -> dict:
        """Reserve one request identity, then run only after the HTTP reply."""
        if not isinstance(request, dict):
            raise _runtime_errors.RunnerError("invalid_request")
        request_id = request.get("request_id")
        try:
            _runtime_utils._id(request_id)
        except (TypeError, ValueError, AttributeError):
            raise _runtime_errors.RunnerError("invalid_request_id") from None
        body = {key: value for key, value in request.items() if key != "request_id"}
        request_hash = (
            "sha256:"
            + hashlib.sha256(
                json.dumps(
                    body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ).encode("utf-8")
            ).hexdigest()
        )
        with self.request_lock:
            for record_path in (self.state / "runs").glob("*/record.json"):
                prior = _runtime_utils._read(record_path)
                if prior.get("client_request_id") == request_id:
                    if prior.get("request_hash") != request_hash:
                        raise _runtime_errors.RunnerError("request_identity_conflict")
                    return prior
            record = self._prepare(
                body, client_request_id=request_id, request_hash=request_hash
            )
            gate = response_gate or threading.Event()
            if response_gate is None:
                gate.set()
            worker = threading.Thread(
                target=self._async_worker,
                args=(record["run_id"], body["task"], gate),
                daemon=True,
            )
            worker.start()
            return record

    def _async_worker(self, run_id, task, gate):
        gate.wait()
        try:
            self._mirror_host_login()
            self._execute(run_id, task, resume=False)
        except _runtime_errors.RunnerError as exc:
            with self.control_lock:
                record = self.status(run_id)
                if record["status"] == "prepared":
                    record.update(status="failed", error_category=str(exc))
                    _runtime_utils._json(self._run_dir(run_id) / "record.json", record)

    def _artifact_source(self, provider, run_id):
        if provider == getattr(self, "provider", "codex"):
            return self._run_dir(run_id) / "post-run", self.status(run_id)
        state = self.artifact_sources.get(provider)
        if state is None:
            raise _artifacts_errors.ArtifactError("foreign_artifact_store_required")
        run = state / "runs" / _runtime_utils._id(run_id)
        if run.is_symlink() or not run.resolve().is_relative_to(state):
            raise _artifacts_errors.ArtifactError("foreign_artifact_store_required")
        record = _runtime_utils._read(run / "record.json")
        if record.get("provider") != provider or record.get("run_id") != run_id:
            raise _artifacts_errors.ArtifactError("artifact_snapshot_mismatch")
        return run / "post-run", record

    def select_artifacts(self, run_id, paths):
        if not isinstance(paths, list) or len(paths) > 32:
            raise _artifacts_errors.ArtifactError("invalid_artifact_selection")
        record = self.status(run_id)
        snapshot = self._run_dir(run_id) / "post-run"
        if record.get("status") != "completed" or _runtime_utils._hash_tree(
            snapshot
        ) != record.get("post_run_hash"):
            raise _artifacts_errors.ArtifactError("artifact_snapshot_mismatch")
        result = []
        for path in paths:
            path = _artifacts_utils.relative_path(path)
            source = snapshot / path
            if not source.is_file() or source.stat().st_size > 1024 * 1024:
                raise _artifacts_errors.ArtifactError(
                    "artifact_file_missing_or_too_large"
                )
            result.append(
                {
                    "provider": getattr(self, "provider", "codex"),
                    "run_id": run_id,
                    "snapshot_hash": record["post_run_hash"],
                    "path": path,
                    "content_hash": "sha256:"
                    + hashlib.sha256(source.read_bytes()).hexdigest(),
                    "destination": "handoff/" + path,
                }
            )
        if _runtime_utils._hash_tree(snapshot) != record["post_run_hash"]:
            raise _artifacts_errors.ArtifactError(
                "artifact_source_changed_during_selection"
            )
        return _artifacts_utils.selections(result)

    def _handoff(self, value):
        if value is None:
            return None
        if not isinstance(value, dict) or set(value) != {
            "execution_id",
            "step",
            "source",
            "workspace_policy",
        }:
            raise _runtime_errors.RunnerError("invalid_handoff_provenance")
        _runtime_utils._id(value["execution_id"])
        if (
            type(value["step"]) is not int
            or value["step"] < 0
            or value["workspace_policy"] != "independent"
        ):
            raise _runtime_errors.RunnerError("invalid_handoff_provenance")
        origin = value["source"]
        if origin is not None:
            if (
                not isinstance(origin, dict)
                or set(origin) != {"provider", "run_id"}
                or origin["provider"] not in {"codex", "opencode", "claude"}
            ):
                raise _runtime_errors.RunnerError("invalid_handoff_origin")
            _runtime_utils._id(origin["run_id"])
        return json.loads(json.dumps(value))

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
            raise _runtime_errors.RunnerError("publication_handoff_resume_denied")
        if not isinstance(task, str) or not task.strip():
            raise _runtime_errors.RunnerError("invalid_task")
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
            != ("split" if self.split_executor else "legacy")
            or record["image"] != self.image
            or record["image_id"] != self.image_id
            or record["cli_version"] != _runtime_settings.CLI_VERSION
            or record["config_sha256"] != _runtime_settings.CONFIG_SHA256
        ):
            raise _runtime_errors.RunnerError("resume_binding_mismatch")
        run_dir = self._run_dir(run_id)
        if activity_attempt_id is not None:
            if not isinstance(activity_attempt_id, str):
                raise _runtime_errors.RunnerError("invalid_activity_attempt_id")
            _runtime_utils._id(activity_attempt_id)
            if (
                run_dir / "activity-attempts" / (activity_attempt_id + ".json")
            ).exists():
                raise _runtime_errors.RunnerError("activity_attempt_already_exists")
        snapshot = run_dir / "post-run"
        workspace = run_dir / "workspace"
        if (
            not snapshot.exists()
            or _runtime_utils._hash_tree(snapshot) != expected_post_run_hash
        ):
            raise _runtime_errors.RunnerError("post_run_snapshot_mismatch")
        if (
            _runtime_utils._hash_tree(workspace, exclude_root_git=self.git_workspace)
            != expected_post_run_hash
        ):
            raise _runtime_errors.RunnerError("workspace_changed_since_snapshot")
        if (
            _runtime_utils._hash_tree(run_dir / "canonical") != record["source_hash"]
            or (run_dir / "store/sentinel.txt").read_text(encoding="utf-8")
            != "STORE-ORIGINAL"
        ):
            raise _runtime_errors.RunnerError("protected_mount_changed")
        if self.auth:
            if record.get("runner_instance_id") != self.instance_id:
                raise _runtime_errors.RunnerError(
                    "resume_after_runner_restart_forbidden"
                )
            _token, current = self.auth.access_token()
            prior = record.get("credential") or {}
            if any(
                current.get(key) != prior.get(key)
                for key in ("credential_ref", "provider_subject_hash")
            ):
                raise _runtime_errors.RunnerError("resume_auth_identity_mismatch")
        return self._execute(
            run_id, task, resume=True, activity_attempt_id=activity_attempt_id
        )

    def _mediator_route(self) -> tuple[str, str]:
        # host.docker.internal -> host loopback is checked by the Windows
        # Docker Desktop probe. Other network layouts need their own check.
        if os.name != "nt" or self.mediator_state is None:
            raise _runtime_errors.RunnerError("mediator_container_route_unverified")
        try:
            status = json.loads(
                (self.mediator_state / "mediator.json").read_text(encoding="utf-8")
            )
            port = status["port"]
            instance = status["instance"]
            if (
                type(port) is not int
                or not 1 <= port <= 65535
                or not re.fullmatch(r"[0-9a-f]{32}", instance)
            ):
                raise ValueError("invalid_mediator_status")
            with urlopen(f"http://127.0.0.1:{port}/v1/health", timeout=2) as response:
                health = json.load(response)
            if health != {"status": "ready", "instance": instance}:
                raise ValueError("mediator_instance_mismatch")
        except (OSError, ValueError, KeyError, TypeError, TimeoutError) as error:
            raise _runtime_errors.RunnerError("mediator_unavailable") from error
        return f"http://host.docker.internal:{port}/v1/mediate", instance

    def _execute(
        self,
        run_id: str,
        task: str,
        *,
        resume: bool,
        activity_attempt_id: str | None = None,
    ) -> dict:
        if activity_attempt_id is not None:
            if not isinstance(activity_attempt_id, str):
                raise _runtime_errors.RunnerError("invalid_activity_attempt_id")
            _runtime_utils._id(activity_attempt_id)
        if not self.lock.acquire(blocking=False):
            raise _runtime_errors.RunnerError("runner_busy")
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
                    raise _runtime_errors.RunnerError("run_not_dispatchable")
                cancelled = threading.Event()
                evidence_offset = (run_dir / "raw-events.jsonl").stat().st_size
                attempt_turn_offset = len(record["turns"])
                import laomedo.activity.runner.feed as _runner_feed

                activity_start = (
                    _runner_feed.line_count(run_dir / "activity-events.jsonl"),
                    _runner_feed.line_count(run_dir / "otel-events.jsonl"),
                )
                import laomedo.activity.runner.feed as _runner_feed

                attempt_id = (
                    activity_attempt_id
                    if resume
                    else record.get("activity_initial_attempt_id")
                ) or str(uuid4())
                attempts = run_dir / "activity-attempts"
                attempts.mkdir(exist_ok=True)
                if (attempts / (attempt_id + ".json")).exists():
                    raise _runtime_errors.RunnerError("activity_attempt_already_exists")
                activity_attempt = {
                    "id": attempt_id,
                    "native_start": activity_start[0],
                    "otel_start": activity_start[1],
                    "native_end": None,
                    "otel_end": None,
                    "fresh_thread": not resume,
                    "usage_baseline": _runner_feed.read_feed(
                        run_dir / "activity-events.jsonl", tail=True
                    )["usage_baseline"],
                    "status": "running",
                    "ended_at": None,
                }
                _runtime_utils._json(
                    attempts / (attempt_id + ".json"), activity_attempt
                )
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
                    "launch_token": launch_token,
                    "supervised": self.supervise_containers,
                    "cleanup_verified": False,
                }
                _runtime_utils._json(run_dir / "record.json", record)
            try:
                workspace_skills.verify(
                    run_dir / "workspace",
                    record["skills"],
                    record.get("skill_git_exclusion", {"enabled": False}),
                )
            except ValueError as exc:
                raise _runtime_errors.RunnerError(str(exc)) from None
            if self.supervise_containers:
                if self.lease_service is None:
                    raise _runtime_errors.RunnerError("lease_service_required")
                try:
                    lease = _leases_client.LeaseClient(
                        self.lease_service,
                        run_id=run_id,
                        name=name,
                        token=launch_token,
                        cancelled=cancelled,
                        mediation_request=record.get("github_scope"),
                    )
                except (OSError, RuntimeError):
                    raise _runtime_errors.RunnerError(
                        "lease_service_unavailable"
                    ) from None
                record["container_ownership"]["lease_instance"] = lease.instance
                record["container_ownership"]["grant_id"] = lease.grant_id
                if self.publication_controller is not None and record.get(
                    "github_scope"
                ):
                    self.publication_controller.register(lease, record)
                with self.control_lock:
                    _runtime_utils._json(run_dir / "record.json", record)
            capability = None
            mediator_url = None
            mediator_instance = None
            if record.get("github_scope") is not None:
                if lease is None or lease.grant_id is None:
                    raise _runtime_errors.RunnerError("mediated_grant_unavailable")
                capability = lease.dir / "grant.secret"
                if capability.is_symlink() or not capability.is_file():
                    raise _runtime_errors.RunnerError("mediated_capability_unavailable")
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
                    raise _runtime_errors.RunnerError("resume_auth_identity_mismatch")
            record["credential"] = auth_summary
            _runtime_utils._json(run_dir / "record.json", record)
            launch_attempted = True
            server = self._open_server(
                run_dir,
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
            _runtime_utils._json(run_dir / "record.json", record)
            initialized = server.request(
                "initialize",
                {
                    "clientInfo": {
                        "name": "laomedo_local_runner",
                        "title": "Laomedo Local Runner",
                        "version": "0.1.0",
                    },
                    **(
                        {"capabilities": {"experimentalApi": True}}
                        if self.split_executor or record.get("output_requirements")
                        else {}
                    ),
                },
            )
            if "result" not in initialized:
                raise _runtime_errors.RunnerError("initialize_rejected")
            server.notify("initialized", {})
            if self.split_executor:
                server.register_executor()
            entries = _runtime_utils._advertised_models(server)
            choice = next(
                (x for x in entries if x["id"] == record["requested_model"]), None
            )
            levels = set((choice or {}).get("efforts", []))
            if choice is None or record["requested_effort"] not in levels:
                raise _runtime_errors.RunnerError("unsupported_model_effort")
            if cancelled.is_set():
                record.update(
                    status="cancelled",
                    error_category="cancelled_before_turn",
                    cancel_requested=True,
                )
                return record
            self._turn_available()
            method = "thread/resume" if resume else "thread/start"
            params = (
                {"threadId": record["thread_id"], "cwd": "/draft"}
                if resume
                else {
                    "model": record["requested_model"],
                    "cwd": "/draft",
                    "approvalPolicy": "never",
                }
            )
            if record.get("output_requirements"):
                server.output_requirements = _contracts_output.verify_requirements(
                    record["output_requirements"]
                )
                if not resume:
                    params["dynamicTools"] = [
                        _contracts_output.dynamic_tool(server.output_requirements)
                    ]
            if self.split_executor:
                params["environments"] = server.thread_environment()
                server.assert_executor_selection(params["environments"])
            response = server.request(method, params)
            result = response.get("result") or {}
            thread = result.get("thread") or {}
            native_id = thread.get("id")
            if not native_id or (resume and native_id != record["thread_id"]):
                raise _runtime_errors.RunnerError("thread_identity_mismatch")
            record["thread_id"] = native_id
            server.active_thread_id = native_id
            record["precheck"]["installed"] = "dynamicTools" in params
            record["effective_model"] = thread.get("model") or result.get("model")
            record["effective_effort"] = result.get("reasoningEffort") or thread.get(
                "reasoningEffort"
            )
            _runtime_utils._json(run_dir / "record.json", record)
            if cancelled.is_set():
                record.update(
                    status="cancelled",
                    error_category="cancelled_before_turn",
                    cancel_requested=True,
                )
                return record
            attempt = self._reserve_turn()
            record["attempt_number"] = attempt
            _runtime_utils._json(run_dir / "record.json", record)
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
            turn_params = {
                "threadId": native_id,
                "model": record["requested_model"],
                "effort": record["requested_effort"],
                "cwd": "/draft",
                "input": [{"type": "text", "text": task}],
            }
            if record.get("output_requirements"):
                turn_params["input"][0]["text"] += (
                    "\nReturn your final submission as a JSON object with explicit task_outcome "
                    "success or failure. Use laomedo_output_precheck on your form before "
                    "handoff and correct rejected fields within this request. Requirements: "
                    + json.dumps(record["output_requirements"], sort_keys=True)
                )
            if self.split_executor:
                server.assert_controller_isolated()
                turn_params["environments"] = server.turn_environment()
                server.assert_executor_selection(turn_params["environments"])
                turn_params["sandboxPolicy"] = {
                    "type": "externalSandbox",
                    "networkAccess": "restricted",
                }
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
                    except _siwc_errors.AuthError as exc:
                        category, outcome = _runtime_utils._auth_record_error(exc)
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
                    raise _siwc_errors.AuthError(auth_failure["code"])
            turn_event_offset = len(server.events)
            sent = server.request("turn/start", turn_params)
            turn_id = ((sent.get("result") or {}).get("turn") or {}).get("id")
            if not turn_id:
                raise _runtime_errors.RunnerError("turn_dispatch_rejected")
            server.active_thread_id = native_id
            status, error = server.wait_turn(turn_id, 180, cancelled)
            # Correction is a continuation of this native thread, never a new
            # dispatch of the original task. Any mediated scope or tool effect
            # blocks automatic continuation because safe repetition is unknown.
            correction_count = 0
            while record.get("output_requirements") and status == "completed":
                try:
                    submission = json.loads(
                        _runtime_utils._answer(server.events[turn_event_offset:])
                        or "null"
                    )
                except (ValueError, TypeError):
                    submission = None
                validation = _contracts_output.evaluate(
                    record["output_requirements"], submission
                )
                record["output_validation"] = validation
                if (
                    validation["contract_status"] == "accepted"
                    or isinstance(submission, dict)
                    and submission.get("task_outcome") == "failure"
                    or correction_count >= record["output_retries"]
                ):
                    break
                commands_before = _runtime_utils._command_summary(
                    server.events, turn_id
                )

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
                _runtime_utils._json(run_dir / "record.json", record)
                feedback = (
                    "Continue this same session by correcting only your output form. "
                    "Do not repeat the original task or any external writes. "
                    "Use the existing output precheck. Validation feedback: "
                    + json.dumps(validation, sort_keys=True)
                )
                turn_params["input"] = [{"type": "text", "text": feedback}]
                if self.split_executor:
                    server.assert_controller_isolated()
                    server.assert_executor_selection(turn_params["environments"])
                if self.auth and not still_authorized():
                    raise _siwc_errors.AuthError(auth_failure["code"])
                turn_event_offset = len(server.events)
                next_turn = server.request("turn/start", turn_params)
                turn_id = ((next_turn.get("result") or {}).get("turn") or {}).get("id")
                if not turn_id:
                    raise _runtime_errors.RunnerError("turn_dispatch_rejected")
                status, error = server.wait_turn(turn_id, 180, cancelled)
            native_status = status
            commands = _runtime_utils._command_summary(server.events, turn_id)
            record["native_turn_status"] = native_status
            record["precheck"]["call_count"] = getattr(server, "precheck_call_count", 0)
            record["command_summary"] = commands
            record["native_answer"] = (
                _runtime_utils._answer(server.events[turn_event_offset:])
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
            native_errors = _runtime_utils._native_error_summary(server.events, turn_id)
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
                _runtime_utils._answer(server.events[turn_event_offset:])
                if status == "completed"
                else None
            )
            if status == "completed" and not record["answer"]:
                raise _runtime_errors.RunnerError("completed_without_agent_message")
            if status == "completed":
                try:
                    workspace_skills.verify(
                        run_dir / "workspace",
                        record["skills"],
                        record.get("skill_git_exclusion", {"enabled": False}),
                    )
                except ValueError as exc:
                    record["answer"] = None
                    raise _runtime_errors.RunnerError(str(exc)) from None
                post_hash = _runtime_utils._hash_tree(
                    run_dir / "workspace", exclude_root_git=self.git_workspace
                )
                pending = run_dir / ("post-run-pending-" + uuid4().hex)
                _runtime_utils._copy_tree(
                    run_dir / "workspace", pending, exclude_root_git=self.git_workspace
                )
                old = run_dir / "post-run"
                if old.exists():
                    workspace_skills.remove_owned_tree(old, self.state)
                pending.rename(old)
                record["post_run_hash"] = post_hash
                record["output_ref"] = f"laomedo:run:{run_id}:workspace"
                record["snapshot_ready"] = True
            if (
                _runtime_utils._hash_tree(run_dir / "canonical")
                != record["source_hash"]
                or (run_dir / "store/sentinel.txt").read_text(encoding="utf-8")
                != "STORE-ORIGINAL"
            ):
                raise _runtime_errors.RunnerError("protected_mount_changed")
            if lease is not None and lease.lost.is_set():
                raise _runtime_errors.RunnerError("lease_service_lost")
        except Exception as exc:
            if record is None:
                raise
            if record["status"] not in {"interrupted", "cancelled"}:
                record["status"] = "failed"
                if isinstance(exc, _siwc_errors.AuthError):
                    category, outcome = _runtime_utils._auth_record_error(exc)
                    record["error_category"] = category
                    if isinstance(record.get("credential"), dict):
                        record["credential"]["auth_outcome"] = outcome
                else:
                    record["error_category"] = (
                        str(exc)
                        if isinstance(exc, _runtime_errors.RunnerError)
                        else type(exc).__name__
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
                    server.close()
                    if record is not None:
                        record["controller_cleanup"] = "confirmed"
                    if record is not None and record.get("status") == "cancelled":
                        record["cancel_confirmed"] = True
            except Exception:
                close_error = True
                if record is not None:
                    record.update(
                        status="failed",
                        error_category="container_termination_unverified",
                    )
                    record["controller_cleanup"] = "unverified"
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
                        verified, detail = _leases_utils.cleanup_exact(
                            _leases_models.ContainerIdentity(
                                name=name, run_id=run_id, token=launch_token
                            )
                        )
                        if lease is not None:
                            # The executor is already removed. Only a trusted
                            # controller can keep its SAME lease through output
                            # validation; no graph bearer can extend it.
                            record["container_ownership"]["cleanup_verified"] = verified
                            record["container_ownership"]["cleanup_detail"] = detail
                            record.update(
                                _runtime_utils._execution_evidence(
                                    run_dir / "raw-events.jsonl",
                                    evidence_offset,
                                    record,
                                    record["turns"][attempt_turn_offset:],
                                    resumed=resume,
                                    streams_closed=(
                                        server is not None
                                        and getattr(server, "reader", None) is not None
                                        and getattr(server, "stderr_reader", None)
                                        is not None
                                        and server.reader.is_alive() is False
                                        and server.stderr_reader.is_alive() is False
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
                        # A failed normal close may have been completed by the
                        # independent supervisor after its pipe closed.
                        if not verified:
                            verified, detail = _leases_utils.cleanup_exact(
                                _leases_models.ContainerIdentity(
                                    name=name, run_id=run_id, token=launch_token
                                )
                            )
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
                                import laomedo.activity.agent_activity.utils as _agent_activity_utils

                                try:
                                    activity_attempt.update(
                                        native_end=_runner_feed.line_count(
                                            run_dir / "activity-events.jsonl"
                                        ),
                                        otel_end=_runner_feed.line_count(
                                            run_dir / "otel-events.jsonl"
                                        ),
                                        status=record["status"],
                                        ended_at=_agent_activity_utils.now(),
                                    )
                                    _runtime_utils._json(
                                        run_dir
                                        / "activity-attempts"
                                        / (activity_attempt["id"] + ".json"),
                                        activity_attempt,
                                    )
                                except OSError:
                                    pass  # An observation failure cannot change execution success.
                            _runtime_utils._json(run_dir / "record.json", record)
                        self.cancel_flags.pop(run_id, None)
                finally:
                    self.lock.release()
        return record
