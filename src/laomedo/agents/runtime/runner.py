"""Provider-neutral durable Agent lifecycle and workspace orchestration."""
from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from urllib.request import urlopen
from uuid import uuid4
import hashlib
import json
import os
import re
import secrets
import threading
import laomedo.agents.artifacts.errors as _artifacts_errors
import laomedo.agents.artifacts.utils as _artifacts_utils
import laomedo.agents.contracts.output as _contracts_output
import laomedo.agents.contracts.models as _contracts_models
import laomedo.agents.runtime.models as _runtime_models
import laomedo.agents.runtime.errors as _runtime_errors
import laomedo.agents.runtime.utils as _runtime_utils
import laomedo.agents.workspace.errors as _agents_workspace_errors
import laomedo.agents.workspace.git as _workspace_git
import laomedo.host.mediation.errors as _mediation_errors
import laomedo.skills.registry.store as _registry_store
import laomedo.skills.registry.utils as _registry_utils
import laomedo.skills.workspace.errors as _skills_workspace_errors
import laomedo.skills.workspace.utils as workspace_skills

class Runner(ABC):
    """Template-method lifecycle; concrete providers own protocol and runtime policy."""

    def __init__(self, state: Path, skill_store: Path, source_workspace: Path, *,
                 lease_service: Path | None = None, github_authority=None,
                 mediator_state: Path | None = None, git_workspace: bool = False,
                 publication_controller=None, artifact_sources=None):
        self.state = _runtime_utils._private(state)
        self.store = _registry_store.SkillStore(skill_store)
        self.source = source_workspace.expanduser().resolve()
        self.git_workspace = git_workspace
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
        # The lease service is started independently of this runner, so a
        # whole-process-tree kill of the runner cannot also kill it.
        self.lease_service = Path(lease_service).resolve() if lease_service else None
        self.artifact_sources = {}
        for provider, source_state in (artifact_sources or {}).items():
            if provider not in _contracts_models.SUPPORTED_PROVIDERS:
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
                self.recover_interrupted(record)
                _runtime_utils._json(record_path, record)
        self.instance_id = str(uuid4())
        self.lock = threading.Lock()
        self.control_lock = threading.Lock()
        self.request_lock = threading.Lock()
        self.cancel_flags = {}

    @property
    @abstractmethod
    def provider(self) -> str:
        """Concrete adapter identity; there is no default provider."""

    @abstractmethod
    def runtime_binding(self) -> _runtime_models.RuntimeBinding:
        """Return this provider's current public record binding, without credentials."""

    @abstractmethod
    def recover_interrupted(self, record: dict) -> None:
        """Clean up exact interrupted resources using only base state/module helpers.

        Called during base construction, before concrete initialization finishes.
        """

    @abstractmethod
    def model_catalog(self) -> dict:
        """Discover provider metadata without dispatching work."""

    @abstractmethod
    def preflight(self) -> dict:
        """Report this provider's readiness and isolation checks."""

    @abstractmethod
    def resume(self, run_id, task, **binding) -> dict:
        """Validate the provider binding before resuming its existing execution."""

    @abstractmethod
    def _execute(self, run_id, task, *, resume, activity_attempt_id=None) -> dict:
        """Execute using the provider's protocol, cancellation and cleanup rules."""

    def editor_model_catalog(self):
        """Provider-owned refresh semantics for an explicit editor discovery request."""
        return self.model_catalog()

    def prepare_resume(self, run_id, body):
        """Validate provider extensions and refresh authentication before HTTP resume."""
        self._mirror_host_login()
        return {}

    @property
    def supports_mediated_github(self) -> bool:
        """Opt in only when the provider actually implements the mediated lease path."""
        return False

    def _mirror_host_login(self):
        """Provider pre-dispatch authentication hook; neutral runners do nothing."""

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
        binding = self.runtime_binding()
        source = self.source
        handoff = self._handoff(request.get("handoff"))
        if "github_scope" in request:
            raise _runtime_errors.RunnerError("github_scope_must_come_from_authority")
        github_ref = request.get("github_authorization_ref")
        if github_ref is not None and (
            self.github_authority is None
            or not self.supports_mediated_github
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
                "provider": binding.provider,
                "handoff": handoff,
                "imported_artifacts": artifacts,
                "requested_model": model,
                "requested_effort": effort,
                "effective_model": None,
                "effective_effort": None,
                **binding.record_fields(),
                "thread_id": None,
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
        if provider == self.provider:
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
                    "provider": self.provider,
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
                or origin["provider"] not in _contracts_models.SUPPORTED_PROVIDERS
            ):
                raise _runtime_errors.RunnerError("invalid_handoff_origin")
            _runtime_utils._id(origin["run_id"])
        return json.loads(json.dumps(value))


    def _freeze_workspace(self, root: Path, record: dict) -> str:
        """Freeze stable files after the caller confirms descendant cleanup.

        Recheck pinned skills and protected mounts at this boundary. Empty
        directories count, so delayed native housekeeping cannot invalidate a
        snapshot taken while its container was still alive.
        """
        try:
            workspace_skills.verify(
                root / "workspace", record["skills"],
                record.get("skill_git_exclusion", {"enabled": False}),
            )
        except ValueError as error:
            raise _runtime_errors.RunnerError(str(error)) from None
        try:
            self._verify_protected_mounts(root, record)
            pending = root / ("post-run-pending-" + uuid4().hex)
            digest = _runtime_utils._copy_tree(
                root / "workspace", pending, exclude_root_git=self.git_workspace,
            )
            previous = root / "post-run"
            if previous.exists():
                workspace_skills.remove_owned_tree(previous, self.state)
            pending.rename(previous)
            return digest
        except _runtime_errors.RunnerError:
            raise
        except Exception:
            raise _runtime_errors.RunnerError("workspace_copy_mismatch") from None

    def _verify_protected_mounts(self, root: Path, record: dict) -> None:
        """Keep one canonical integrity check for live and closed run boundaries."""
        if (
            _runtime_utils._hash_tree(root / "canonical") != record["source_hash"]
            or (root / "store/sentinel.txt").read_text(encoding="utf-8")
            != "STORE-ORIGINAL"
        ):
            raise _runtime_errors.RunnerError("protected_mount_changed")

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
