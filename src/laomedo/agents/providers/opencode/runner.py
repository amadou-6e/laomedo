"""OpenCode provider adapter. Production Docker/auth deployment is intentionally gated."""

from __future__ import annotations

from urllib import request
from urllib.parse import urlencode
from urllib.parse import urlsplit
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


class OpenCodeHTTP:
    """Private server protocol, usable for credential-free contract verification.

    A caller must provision a private server with controller/tool isolation before
    exposing real credentials. This adapter never reads or imports personal auth.
    """

    def __init__(self, url, directory, evidence):
        parsed = urlsplit(url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise _runtime_errors.RunnerError("private_opencode_server_required")
        self.url = url.rstrip("/")
        self.directory = directory
        self.log = (evidence / "raw-events.jsonl").open("a", encoding="utf-8")

    def call(self, method, path, payload=None):
        req = request.Request(
            self.url + path + "?" + urlencode({"directory": self.directory}),
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method=method,
        )
        with request.urlopen(req, timeout=180) as response:
            value = json.load(response)
        self.log.write(
            json.dumps({"method": method, "path": path, "response": value}) + "\n"
        )
        self.log.flush()
        return value

    def close(self):
        self.log.close()


class OpenCodeRunner(_runtime_runner.Runner):
    """Reuse immutable skills, snapshot lifecycle and bounded dispatch accounting.

    No production transport is installed by default: mounting authentication with
    native OpenCode shell tools would expose it to the model's command execution.
    """

    provider = "opencode"

    def __init__(self, state, skill_store, source_workspace, *, transport_factory=None,
                 lease_service=None, github_authority=None, mediator_state=None,
                 git_workspace=False, publication_controller=None, artifact_sources=None):
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
            provider=self.provider, profile=None, image=None, image_id=None,
            execution_mode="opencode_http", cli_version="opencode " + _opencode_settings.CLI_VERSION,
            config_sha256=None)

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
                health = backend.call("GET", "/global/health")
                if (
                    health.get("version") != _opencode_settings.CLI_VERSION
                    or health.get("healthy") is not True
                ):
                    raise _runtime_errors.RunnerError("opencode_runtime_pin_mismatch")
                providers = backend.call("GET", "/provider")
                connected = providers.get("connected", [])
                models = []
                for provider in providers.get("all", []):
                    if provider.get("id") not in connected:
                        continue
                    for model in provider.get("models", {}):
                        identity = provider["id"] + "/" + model
                        self._validate_provider(identity, "default")
                        models.append({"id": identity, "efforts": ["default"]})
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
        native_capture = None
        baseline_ids = set()
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
            health = backend.call("GET", "/global/health")
            if health.get(
                "version"
            ) != _opencode_settings.CLI_VERSION or not health.get("healthy"):
                raise _runtime_errors.RunnerError("opencode_runtime_pin_mismatch")
            provider, model = record["requested_model"].split("/", 1)
            catalog = backend.call("GET", "/provider")
            available = next(
                (item for item in catalog.get("all", []) if item.get("id") == provider),
                {},
            )
            if provider not in catalog.get(
                "connected", []
            ) or model not in available.get("models", {}):
                raise _runtime_errors.RunnerError("opencode_model_not_connected")
            if flag.is_set():
                raise _runtime_errors.RunnerError("opencode_cancelled_before_dispatch")
            self._turn_available()
            if not resume:
                session = backend.call(
                    "POST", "/session", {"title": "Laomedo private run"}
                )
                record["thread_id"] = session.get("id")
            if not re.fullmatch(r"ses_[a-zA-Z0-9]+", str(record.get("thread_id", ""))):
                raise _runtime_errors.RunnerError("opencode_session_identity_invalid")
            if resume:
                previous = backend.call(
                    "GET", "/session/" + record["thread_id"] + "/message"
                )
                if not isinstance(previous, list):
                    raise _runtime_errors.RunnerError("opencode_history_invalid")
                baseline_ids = {
                    entry.get("info", {}).get("id")
                    for entry in previous
                    if isinstance(entry, dict)
                }
            if flag.is_set():
                raise _runtime_errors.RunnerError("opencode_cancelled_before_dispatch")
            check_auth = getattr(backend, "check_auth_fresh", None)
            if check_auth is not None:
                check_auth()
            if callable(getattr(backend, "open_events", None)):
                import laomedo.activity.opencode.events as _opencode_events
                import laomedo.activity.opencode.projection as _opencode_projection

                try:
                    children = backend.call(
                        "GET", "/session/" + record["thread_id"] + "/children"
                    )
                    for child in children:
                        if (
                            not isinstance(child, dict)
                            or child.get("parentID") != record["thread_id"]
                        ):
                            continue
                        for entry in backend.call(
                            "GET", "/session/" + child["id"] + "/message"
                        ):
                            baseline_ids.add(entry.get("info", {}).get("id"))
                    native_capture = _opencode_events.NativeCapture(
                        root, record["thread_id"], baseline_ids
                    )
                    native_capture.append(
                        {
                            "method": "opencode/modelCatalog",
                            "params": {
                                "model": record["requested_model"],
                                "rates": available["models"][model].get("cost"),
                            },
                        }
                    )
                    native_capture.start(backend)
                except Exception:
                    attempt["capture_error"] = (
                        "opencode_native_subscription_unavailable"
                    )
            record["attempt_number"] = self._reserve_turn()
            _runtime_utils._json(root / "record.json", record)
            if flag.is_set():
                raise _runtime_errors.RunnerError("opencode_cancelled_before_dispatch")
            message = backend.call(
                "POST",
                "/session/" + record["thread_id"] + "/message",
                {
                    "model": {"providerID": provider, "modelID": model},
                    "parts": [{"type": "text", "text": task}],
                },
            )
            info = message.get("info") or {}
            if (
                info.get("sessionID") != record["thread_id"]
                or info.get("providerID") != provider
                or info.get("modelID") != model
            ):
                raise _runtime_errors.RunnerError("opencode_response_identity_mismatch")
            steps = backend.call("GET", "/session/" + record["thread_id"] + "/message")
            import laomedo.activity.opencode.projection as _opencode_projection

            if not isinstance(steps, list):
                raise _runtime_errors.RunnerError("opencode_history_invalid")
            captured = [
                entry
                for entry in steps
                if isinstance(entry, dict)
                and entry.get("info", {}).get("id") not in baseline_ids
            ]
            try:
                if not _opencode_projection.retain_messages(
                    root, record["thread_id"], captured, writer=native_capture
                ):
                    attempt["capture_error"] = "opencode_native_snapshot_size_limit"
            except (OSError, TypeError, ValueError):
                attempt["capture_error"] = "opencode_native_snapshot_unavailable"
            if native_capture:
                native_capture.terminal.wait(2)
                try:
                    children = backend.call(
                        "GET", "/session/" + record["thread_id"] + "/children"
                    )
                    for child in children:
                        if (
                            not isinstance(child, dict)
                            or child.get("parentID") != record["thread_id"]
                        ):
                            continue
                        child_messages = backend.call(
                            "GET", "/session/" + child["id"] + "/message"
                        )
                        new_messages = [
                            entry
                            for entry in child_messages
                            if entry.get("info", {}).get("id") not in baseline_ids
                        ]
                        if new_messages:
                            with native_capture.lock:
                                native_capture.child_idle.setdefault(child["id"], False)
                            native_capture.append(
                                {
                                    "method": "opencode/sessionSnapshot",
                                    "params": {"session": child},
                                }
                            )
                            _opencode_projection.retain_messages(
                                root,
                                child["id"],
                                new_messages,
                                parent=record["thread_id"],
                                writer=native_capture,
                            )
                except Exception:
                    attempt["capture_error"] = "opencode_child_snapshot_incomplete"
            observed = dict(message)
            observed["parts"] = _opencode_utils.turn_parts(message, steps)
            normalized = _opencode_utils.normalize_message(observed, record["skills"])
            record["skill"] = (
                record["skills"][0] if len(record["skills"]) == 1 else None
            )
            if flag.is_set():
                record["status"] = "cancelled"
            else:
                self._verify_pinned_skills(root / "workspace", record)
                record.update(
                    normalized,
                    status="completed",
                    effective_model=info["providerID"] + "/" + info["modelID"],
                    effective_effort=None,
                )
                pending = root / "post-run-pending"
                post_hash = _runtime_utils._copy_tree(root / "workspace", pending)
                old = root / "post-run"
                if old.exists():
                    workspace_skills.remove_owned_tree(old, self.state)
                pending.rename(old)
                record.update(
                    post_run_hash=post_hash,
                    snapshot_ready=True,
                    output_ref=f"laomedo:run:{run_id}:workspace",
                )
            record["turns"].append(
                {
                    "turn_id": normalized["native_turn_id"],
                    "status": record["status"],
                    "input_hash": "sha256:" + hashlib.sha256(task.encode()).hexdigest(),
                }
            )
            if (
                _runtime_utils._hash_tree(root / "canonical") != record["source_hash"]
                or (root / "store/sentinel.txt").read_text(encoding="utf-8")
                != "STORE-ORIGINAL"
            ):
                raise _runtime_errors.RunnerError("protected_mount_changed")
        except Exception as exc:
            if record is None or attempt is None:
                raise
            record.update(
                status="cancelled" if flag is not None and flag.is_set() else "failed",
                error_category=(
                    None if flag is not None and flag.is_set() else (
                        str(exc) if isinstance(exc, _runtime_errors.RunnerError)
                        else type(exc).__name__
                    )
                ),
            )
        finally:
            try:
                if native_capture:
                    try:
                        native_capture.close()
                    except Exception:
                        attempt["capture_error"] = (
                            "opencode_native_reader_cleanup_unverified"
                        )
                    attempt["native_stream_complete"] = native_capture.complete
                    if native_capture.error or not native_capture.complete:
                        attempt.setdefault(
                            "capture_error",
                            native_capture.error
                            or "opencode_native_terminal_not_observed",
                        )
                if backend:
                    backend.close()
                if (
                    native_capture
                    and native_capture.thread
                    and native_capture.thread.is_alive()
                ):
                    native_capture.thread.join(5)
                    if native_capture.thread.is_alive():
                        attempt["capture_error"] = (
                            "opencode_native_reader_cleanup_unverified"
                        )
                        attempt["native_stream_complete"] = False
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
            acknowledged = backend.call(
                "POST", "/session/" + record["thread_id"] + "/abort", {}
            )
            if acknowledged is not True:
                raise _runtime_errors.RunnerError("opencode_abort_not_acknowledged")
            # An acknowledgement is not proof that a native child command terminated.
            return {
                **record,
                "cancel_requested": True,
                "cancel_acknowledged": True,
                "termination_verified": False,
            }
        return record
