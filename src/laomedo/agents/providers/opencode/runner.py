"""OpenCode provider adapter. Production Docker/auth deployment is intentionally gated."""

from __future__ import annotations

from uuid import uuid4
import hashlib
import json
import laomedo.activity.agent_activity.utils as _agent_activity_utils
import laomedo.activity.runner.feed as _runner_feed
import laomedo.agents.providers.opencode.settings as _opencode_settings
import laomedo.agents.providers.opencode.utils as _opencode_utils
import laomedo.agents.runtime.errors as _runtime_errors
import laomedo.agents.runtime.runner as _runtime_runner
import laomedo.agents.runtime.models as _runtime_models
import laomedo.agents.runtime.utils as _runtime_utils
import laomedo.skills.registry.errors as _registry_errors
import laomedo.skills.registry.utils as _registry_utils
import laomedo.skills.workspace.utils as workspace_skills
import re
import shutil
import threading
import time


class OpenCodeRunner(_runtime_runner.Runner):
    """Reuse immutable skills, snapshot lifecycle and bounded dispatch accounting.

    No production transport is installed by default: mounting authentication with
    native OpenCode shell tools would expose it to the model's command execution.
    """

    provider = "opencode"

    def __init__(
        self,
        state,
        skill_store,
        source_workspace,
        *,
        transport_factory=None,
        lease_service=None,
        github_authority=None,
        mediator_state=None,
        git_workspace=False,
        publication_controller=None,
        artifact_sources=None,
    ):
        self.transport_factory = transport_factory
        self.active_backends = {}
        self._opencode_catalog_lock = threading.Lock()
        self._opencode_catalog_cached = None
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
        self._recover_containers()

    def runtime_binding(self):
        return _runtime_models.RuntimeBinding(
            provider=self.provider,
            profile=None,
            image=None,
            image_id=None,
            execution_mode="opencode_acp",
            cli_version="opencode " + _opencode_settings.CLI_VERSION,
            config_sha256=None,
        )

    def recover_interrupted(self, record):
        """Constructor recovery reconciles receipts across prior runs before dispatch."""

    def _recover_containers(self):
        """Recover central and legacy run/catalogue receipts before new dispatch."""
        if self.transport_factory is None or self.lock.locked():
            return
        pending = [
            *self.state.glob("receipts/*.json"),
            *self.state.glob("runs/*/docker-receipts/*.json"),
            *self.state.glob("catalog/*/docker-receipts/*.json"),
        ]
        if not pending:
            return
        try:
            from py_docker import Client
            from py_docker.errors import DockerOperationError
        except ImportError:
            raise _runtime_errors.RunnerError(
                "opencode_container_cleanup_unverified"
            ) from None
        try:
            with Client() as docker:
                for receipt in pending:
                    docker.sessions.recover(receipt)
        except DockerOperationError:
            raise _runtime_errors.RunnerError(
                "opencode_container_cleanup_unverified"
            ) from None

    def model_catalog(self):
        """Discover connected native models without creating a session or turn."""
        if self.transport_factory is None:
            raise _runtime_errors.RunnerError("opencode_isolated_transport_required")
        self._recover_containers()
        with self._opencode_catalog_lock:
            cached = self._opencode_catalog_cached
            if cached and time.monotonic() - cached[0] < 30:
                return cached[1]
            if not self.lock.acquire(blocking=False):
                raise _runtime_errors.RunnerError("runner_busy")
            root = self.state / "catalog" / str(uuid4())
            backend = None
            try:
                for name in ("workspace", "canonical", "store"):
                    (root / name).mkdir(parents=True)
                (root / "workspace/.agents/skills").mkdir(parents=True)
                backend = self.transport_factory(root / "workspace", root)
                models = [
                    {"id": item["id"], "efforts": item["efforts"]}
                    for item in backend.models()
                ]
                for item in models:
                    self._validate_provider(item["id"], "default")
                if not models:
                    raise _runtime_errors.RunnerError("opencode_model_not_connected")
                result = {"models": models, "submitted_turns": 0}
            finally:
                try:
                    if backend is not None:
                        backend.close()
                finally:
                    try:
                        if root.exists() and not list(
                            root.joinpath("docker-receipts").glob("*.json")
                        ):
                            shutil.rmtree(root)
                    finally:
                        self.lock.release()
            self._opencode_catalog_cached = (time.monotonic(), result)
            return result

    def _prepare(self, request, **kwargs):
        # Both blocking and asynchronous starts must validate before preparing
        # a workspace or accepting a request identity.
        if not isinstance(request, dict):
            raise _runtime_errors.RunnerError("invalid_request")
        self._validate_provider(request.get("model"), request.get("effort"))
        if self.transport_factory is None:
            raise _runtime_errors.RunnerError("opencode_isolated_transport_required")
        if request.get("output_requirements") is not None:
            raise _runtime_errors.RunnerError(
                "opencode_output_requirements_not_supported"
            )
        self._recover_containers()
        return super()._prepare(request, **kwargs)

    def preflight(self):
        """Report transport configuration without launching an authenticated backend.

        transport_configured is not a health or authentication attestation.
        Backend startup and catalogue/turn discovery perform the active checks;
        retain this configuration-only boundary and its existing public payload.
        """
        if self.transport_factory is None:
            return {
                "provider": "opencode",
                "cli_version": _opencode_settings.CLI_VERSION,
                "status": "blocked",
                "error_category": "opencode_isolated_transport_required",
                "submitted_turns": 0,
            }
        return {
            "provider": "opencode",
            "cli_version": _opencode_settings.CLI_VERSION,
            "status": "transport_configured",
            "submitted_turns": 0,
        }

    @staticmethod
    def _validate_provider(model, effort):
        if not isinstance(model, str) or not re.fullmatch(
            r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.:-]+", model
        ):
            raise _runtime_errors.RunnerError("opencode_provider_model_required")
        if effort != "default":
            raise _runtime_errors.RunnerError("unsupported_opencode_effort")

    def _materialize(self, workspace, ref):
        # OpenCode skill names have a narrower grammar than the shared registry.
        if not isinstance(ref, dict) or not re.fullmatch(
            r"[a-z0-9]+(?:-[a-z0-9]+)*", str(ref.get("skill_id", ""))
        ):
            raise _runtime_errors.RunnerError("unsupported_opencode_skill_name")
        return super()._materialize(workspace, ref)

    def _verify_pinned_skills(self, workspace, record):
        skills = record.get("skills")
        if not isinstance(skills, list):
            raise _runtime_errors.RunnerError("pinned_skill_record_invalid")
        expected = {
            skill.get("skill_id"): skill.get("tree_hash")
            for skill in skills
            if isinstance(skill, dict)
        }
        if len(expected) != len(skills) or any(
            not isinstance(name, str) or not isinstance(digest, str)
            for name, digest in expected.items()
        ):
            raise _runtime_errors.RunnerError("pinned_skill_record_invalid")
        root = workspace / ".agents" / "skills"
        try:
            entries = list(root.iterdir())
            if {entry.name for entry in entries} != set(expected) or len(
                entries
            ) != len(expected):
                raise _runtime_errors.RunnerError("pinned_skill_workspace_changed")
            for skill in skills:
                name, digest = skill["skill_id"], skill["tree_hash"]
                if (
                    skill.get("revision_id") != digest
                    or self.store.revision(name, digest)["tree_hash"] != digest
                ):
                    raise _runtime_errors.RunnerError("pinned_skill_record_invalid")
                if (
                    _registry_utils.tree_hash(_registry_utils.inventory(root / name))
                    != digest
                ):
                    raise _runtime_errors.RunnerError("pinned_skill_workspace_changed")
        except (OSError, _registry_errors.SkillStoreError) as exc:
            raise _runtime_errors.RunnerError("pinned_skill_workspace_changed") from exc
        try:
            workspace_skills.verify(
                workspace, skills, record.get("skill_git_exclusion", {"enabled": False})
            )
        except ValueError as exc:
            raise _runtime_errors.RunnerError(str(exc)) from None

    def resume(
        self,
        run_id,
        task,
        *,
        expected_post_run_hash,
        expected_thread_id,
        model,
        effort,
        activity_attempt_id=None,
    ):
        self._validate_provider(model, effort)
        record = self.status(run_id)
        if (
            record.get("provider") != "opencode"
            or record.get("runtime_version") != _opencode_settings.CLI_VERSION
            or record["status"] != "completed"
            or record["thread_id"] != expected_thread_id
            or record["post_run_hash"] != expected_post_run_hash
            or record["requested_model"] != model
            or record["requested_effort"] != effort
            or not isinstance(task, str)
            or not task.strip()
        ):
            raise _runtime_errors.RunnerError("resume_binding_mismatch")
        root = self._run_dir(run_id)
        if (
            _runtime_utils._hash_tree(root / "post-run") != expected_post_run_hash
            or _runtime_utils._hash_tree(root / "workspace") != expected_post_run_hash
        ):
            raise _runtime_errors.RunnerError("workspace_changed_since_snapshot")
        if (
            _runtime_utils._hash_tree(root / "canonical") != record["source_hash"]
            or (root / "store/sentinel.txt").read_text(encoding="utf-8")
            != "STORE-ORIGINAL"
        ):
            raise _runtime_errors.RunnerError("protected_mount_changed")
        self._verify_pinned_skills(root / "workspace", record)
        return self._execute(
            run_id, task, resume=True, activity_attempt_id=activity_attempt_id
        )

    def _execute(self, run_id, task, *, resume, activity_attempt_id=None):
        if activity_attempt_id is not None:
            _runtime_utils._id(activity_attempt_id)
        if not self.lock.acquire(blocking=False):
            # A model refresh is not an agent run. Wait for its bounded cleanup
            # instead of rejecting Run while metadata owns the profile lock.
            if not self._opencode_catalog_lock.acquire(timeout=30):
                raise _runtime_errors.RunnerError(
                    "opencode_model_discovery_in_progress"
                )
            self._opencode_catalog_lock.release()
            if not self.lock.acquire(blocking=False):
                raise _runtime_errors.RunnerError("runner_busy")
        root, record, flag, backend, attempt = None, None, None, None, None
        reader = capture = baseline = None
        baseline_available = True
        metadata_cleanup_unverified = False
        catalog = []
        launch_attempted = False
        try:
            root, record = self._run_dir(run_id), self.status(run_id)
            with self.control_lock:
                record = self.status(run_id)
                if record["status"] == "cancelled" and record.get("cancel_confirmed"):
                    return record
                if record["status"] != ("completed" if resume else "prepared"):
                    raise _runtime_errors.RunnerError("run_not_dispatchable")
                # Refusal must preserve a completed run and its resume snapshot.
                self._turn_available()
                attempt_id = (
                    activity_attempt_id
                    if resume
                    else record.get("activity_initial_attempt_id")
                ) or str(uuid4())
                _runtime_utils._id(attempt_id)
                attempts = root / "activity-attempts"
                attempts.mkdir(exist_ok=True)
                if (attempts / (attempt_id + ".json")).exists():
                    raise _runtime_errors.RunnerError("activity_attempt_already_exists")
                attempt = {
                    "id": attempt_id,
                    "native_start": _runner_feed.line_count(
                        root / "activity-events.jsonl"
                    ),
                    "otel_start": _runner_feed.line_count(root / "otel-events.jsonl"),
                    "native_end": None,
                    "otel_end": None,
                    "usage_baseline": {},
                    "status": "running",
                    "ended_at": None,
                }
                _runtime_utils._json(attempts / (attempt_id + ".json"), attempt)
                flag = threading.Event()
                self.cancel_flags[run_id] = flag
                record.update(
                    activity_attempt_id=attempt_id,
                    attempt_finished=False,
                    snapshot_ready=False,
                    post_run_hash=None,
                    output_ref=None,
                    controller_cleanup="not_started",
                    evidence_complete="unknown",
                )
                record.update(
                    provider="opencode",
                    runtime_version=_opencode_settings.CLI_VERSION,
                    profile=None,
                    image=None,
                    image_id=None,
                    cli_version="opencode " + _opencode_settings.CLI_VERSION,
                    config_sha256=None,
                    status="running",
                )
                _runtime_utils._json(root / "record.json", record)
            self._verify_pinned_skills(root / "workspace", record)
            if flag.is_set():
                raise _runtime_errors.RunnerError("opencode_cancelled_before_dispatch")
            launch_attempted = True
            backend = self.transport_factory(root / "workspace", root)
            self.active_backends[run_id] = backend
            identity = getattr(
                backend,
                "runtime_identity",
                {
                    "provider": "opencode",
                    "runtime_version": _opencode_settings.CLI_VERSION,
                },
            )
            if resume and record.get("provider_runtime") != identity:
                raise _runtime_errors.RunnerError("resume_provider_binding_mismatch")
            record["provider_runtime"] = identity
            catalog = backend.models()
            if record["requested_model"] not in {item["id"] for item in catalog}:
                raise _runtime_errors.RunnerError("opencode_model_not_connected")
            if flag.is_set():
                raise _runtime_errors.RunnerError("opencode_cancelled_before_dispatch")
            reader = backend.history_reader()
            from laomedo.agents.providers.opencode.history.errors import HistoryError
            if resume and reader is not None:
                try:
                    baseline = reader.read(record["thread_id"])
                except _runtime_errors.RunnerError:
                    metadata_cleanup_unverified = True
                    raise  # Owned metadata-job cleanup uncertainty remains fatal.
                except HistoryError as error:
                    baseline_available = False
                    attempt["capture_error"] = error.code
                    record["evidence_complete"] = "partial"
                except Exception:
                    baseline_available = False
                    attempt["capture_error"] = "opencode_native_snapshot_unavailable"
                    record["evidence_complete"] = "partial"
            from laomedo.activity.acp.capture import AcpCapture

            capture = AcpCapture(root, attempt_id)

            def bind(session_id):
                """Persist the actual native binding before submitting the prompt."""
                record["thread_id"] = session_id
                record["communication_protocol"] = "acp.v1"
                _runtime_utils._json(root / "record.json", record)

            # Discovery can take long enough for a bounded credential to expire.
            # Recheck before charging or submitting a turn.
            backend.check_auth_fresh()
            record["attempt_number"] = self._reserve_turn()
            _runtime_utils._json(root / "record.json", record)
            outcome = backend.run(
                task,
                model=record["requested_model"],
                session_id=record.get("thread_id") if resume else None,
                cancelled=flag,
                capture=capture,
                on_session=bind,
            )
            normalized = {
                "answer": outcome.answer,
                "native_turn_id": None,
                "usage": outcome.usage,
                "tools": outcome.tool_calls(),
            }
            if not flag.is_set():
                if outcome.stop_reason != "end_turn":
                    raise _runtime_errors.RunnerError("opencode_response_not_terminal")
                if any(
                    tool["status"] not in {"completed", "failed"}
                    for tool in normalized["tools"]
                ):
                    raise _runtime_errors.RunnerError("opencode_outstanding_tool")
            if not normalized["answer"] and not flag.is_set():
                raise _runtime_errors.RunnerError("completed_without_agent_message")
            if flag.is_set():
                record["status"] = "cancelled"
            else:
                self._verify_pinned_skills(root / "workspace", record)
                record.update(
                    normalized,
                    status="completed",
                    effective_model=record["requested_model"],
                    effective_effort=None,
                )
            record["turns"].append(
                {
                    "turn_id": attempt_id,
                    "identity_source": "host_attempt",
                    "status": record["status"],
                    "input_hash": "sha256:" + hashlib.sha256(task.encode()).hexdigest(),
                }
            )
            self._verify_protected_mounts(root, record)
        except Exception as exc:
            if record is None or attempt is None:
                raise
            record.update(
                status="cancelled" if flag is not None and flag.is_set() else "failed",
                error_category=(
                    None
                    if flag is not None and flag.is_set()
                    else (
                        str(exc)
                        if isinstance(exc, _runtime_errors.RunnerError)
                        else type(exc).__name__
                    )
                ),
            )
        finally:
            try:
                if backend:
                    backend.close()
                    if metadata_cleanup_unverified:
                        backend.termination_verified = False
                        raise _runtime_errors.RunnerError(
                            "opencode_container_cleanup_unverified"
                        )
                if (
                    reader is not None
                    and capture is not None
                    and capture.session_id is not None
                    and baseline_available
                ):
                    capture.seal()
                    try:
                        history = reader.read(capture.session_id)
                        reader.retain(history, baseline, capture, catalog)
                        record.update(history.record_fields(baseline))
                        if record["status"] == "completed":
                            if not record.get("answer"):
                                record.update(
                                    status="failed",
                                    error_category="completed_without_agent_message",
                                )
                            elif any(
                                tool["status"] not in {"completed", "error"}
                                for tool in record["tools"]
                            ):
                                record.update(
                                    status="failed",
                                    error_category="opencode_outstanding_tool",
                                )
                        for tool in record["tools"]:
                            inputs = tool.get("input")
                            if (
                                tool["tool"] == "skill"
                                and tool["status"] == "completed"
                                and isinstance(inputs, dict)
                            ):
                                for skill in record["skills"]:
                                    if inputs.get("name") == skill["skill_id"]:
                                        skill["use_evidence"] = (
                                            "native_skill_tool_completed"
                                        )
                        record["skill"] = (
                            record["skills"][0] if len(record["skills"]) == 1 else None
                        )
                        if (
                            record["turns"]
                            and record["turns"][-1]["turn_id"] == attempt["id"]
                        ):
                            record["turns"][-1]["native_turn_id"] = record.get(
                                "native_turn_id"
                            )
                        complete = capture.finished and history.terminal_complete(
                            baseline
                        )
                        attempt["capture_complete"] = complete
                        record["evidence_complete"] = (
                            "complete" if complete else "partial"
                        )
                    except HistoryError as error:
                        attempt["capture_error"] = error.code
                        record["evidence_complete"] = "partial"
                    except _runtime_errors.RunnerError:
                        backend.termination_verified = False
                        raise
                    except Exception:
                        attempt["capture_error"] = (
                            "opencode_native_snapshot_unavailable"
                        )
                        record["evidence_complete"] = "partial"
                if record is not None and record.get("status") == "completed":
                    record.update(post_run_hash=self._freeze_workspace(root, record), snapshot_ready=True,
                        output_ref=f"laomedo:run:{run_id}:workspace")
                if record is not None and attempt is not None:
                    try:
                        import laomedo.activity.opencode.telemetry as _opencode_telemetry

                        attempt["telemetry_complete"] = (
                            _opencode_telemetry.export_attempt(
                                root,
                                attempt["native_start"],
                                record["thread_id"],
                                record["requested_model"],
                            )
                        )
                    except Exception:
                        attempt["telemetry_complete"] = False
                        attempt.setdefault(
                            "capture_error", "opencode_adapter_telemetry_incomplete"
                        )
                if record is not None:
                    record["controller_cleanup"] = (
                        "confirmed"
                        if backend is not None
                        and getattr(backend, "termination_verified", False)
                        else "unverified"
                    )
                    if record.get("status") == "cancelled":
                        record["cancel_confirmed"] = not launch_attempted or (
                            backend is not None
                            and getattr(backend, "termination_verified", False)
                        )
            except Exception as error:
                if record is not None:
                    verified = backend is not None and getattr(
                        backend, "termination_verified", False
                    )
                    record.update(
                        status="failed",
                        error_category=str(error)
                        if isinstance(error, _runtime_errors.RunnerError)
                        else "opencode_transport_cleanup_failed",
                        controller_cleanup="confirmed" if verified else "unverified",
                        cancel_confirmed=False,
                    )
            finally:
                try:
                    if record is not None and attempt is not None:
                        with self.control_lock:
                            record["attempt_finished"] = True
                            record["cancel_requested"] = bool(
                                flag is not None and flag.is_set()
                            )
                            if record.get("status") != "completed":
                                record.update(
                                    snapshot_ready=False,
                                    post_run_hash=None,
                                    output_ref=None,
                                )
                            attempt.update(
                                native_end=_runner_feed.line_count(
                                    root / "activity-events.jsonl"
                                ),
                                otel_end=_runner_feed.line_count(
                                    root / "otel-events.jsonl"
                                ),
                                status=record["status"],
                                ended_at=_agent_activity_utils.now(),
                            )
                            _runtime_utils._json(
                                root / "activity-attempts" / (attempt["id"] + ".json"),
                                attempt,
                            )
                            _runtime_utils._json(root / "record.json", record)
                finally:
                    self.active_backends.pop(run_id, None)
                    self.cancel_flags.pop(run_id, None)
                    self.lock.release()
        return record

    def cancel(self, run_id):
        record = self.status(run_id)
        if record["status"] == "prepared":
            with self.control_lock:
                record = self.status(run_id)
                if record["status"] == "prepared":
                    record.update(
                        status="cancelled",
                        cancel_requested=True,
                        cancel_confirmed=True,
                        cancel_acknowledged=True,
                        attempt_finished=True,
                        controller_cleanup="not_launched",
                    )
                    _runtime_utils._json(self._run_dir(run_id) / "record.json", record)
                    return record
        if record["status"] == "running":
            flag = self.cancel_flags.get(run_id)
            if flag is None:
                current = self.status(run_id)
                if current["status"] != "running":
                    return current
                raise _runtime_errors.RunnerError("run_not_active_in_this_process")
            with self.control_lock:
                current = self.status(run_id)
                if current["status"] != "running":
                    return current
                flag.set()
                current["cancel_requested"] = True
                _runtime_utils._json(self._run_dir(run_id) / "record.json", current)
                record = current
            backend = self.active_backends.get(run_id)
            if backend is None or not record.get("thread_id"):
                return {
                    **record,
                    "cancel_requested": True,
                    "cancel_acknowledged": False,
                    "termination_verified": False,
                }
            backend.cancel()
            # An acknowledgement is not proof that a native child command terminated.
            return {
                **record,
                "cancel_requested": True,
                "cancel_acknowledged": False,
                "termination_verified": False,
            }
        return record
