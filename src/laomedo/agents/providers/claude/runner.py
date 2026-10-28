"""Isolated Claude Code runner with persistent sessions and streamed native events."""

from __future__ import annotations

from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeout
from copy import deepcopy
from pathlib import Path
from uuid import UUID
from uuid import uuid4
import hashlib
import json
import laomedo.activity.agent_activity.utils as _agent_activity_utils
import laomedo.activity.runner.feed as _runner_feed
import laomedo.agents.contracts.output as _contracts_output
import laomedo.agents.providers.claude.catalog as _claude_catalog
import laomedo.agents.providers.claude.settings as _claude_settings
import laomedo.agents.providers.claude.container as _claude_container
import laomedo.agents.providers.claude.utils as _agents_providers_claude_utils
import laomedo.agents.runtime.errors as _runtime_errors
import laomedo.agents.runtime.runner as _runtime_runner
import laomedo.agents.runtime.models as _runtime_models
import laomedo.agents.runtime.utils as _runtime_utils
import laomedo.host.credentials.claude.errors as _claude_errors
import laomedo.host.credentials.claude.utils as _host_credentials_claude_utils
import laomedo.host.leases.models as _leases_models
import laomedo.host.leases.utils as _leases_utils
import laomedo.skills.registry.utils as _registry_utils
import laomedo.skills.workspace.utils as workspace_skills
import laomedo.host.credentials.claude.settings as _host_claude_settings
import re
import subprocess
import threading
import time


class ClaudeRunner(_runtime_runner.Runner):
    provider = "claude"

    def editor_model_catalog(self):
        return self.model_catalog(refresh=True)

    def prepare_resume(self, run_id, body):
        extra = {}
        if "run_timeout_seconds" in body:
            value = body["run_timeout_seconds"]
            if type(value) is not int or not 1 <= value <= 86400:
                raise _runtime_errors.RunnerError("claude_turn_timeout_invalid")
            extra["run_timeout_seconds"] = value
        required = extra.get("run_timeout_seconds") if extra else self.status(run_id).get("turn_timeout", self.turn_timeout)
        self._mirror_host_login(minimum_validity_seconds=required)
        return extra

    def runtime_binding(self):
        return _runtime_models.RuntimeBinding(
            provider=self.provider, profile=self.profile, image=self.image, image_id=self.image_id,
            execution_mode="claude_container", cli_version="Claude Code " + _claude_settings.CLI_VERSION,
            config_sha256=None)

    def recover_interrupted(self, record):
        # The independent lease supervisor owns controller/worker lifetimes.
        # Reconcile the exact persisted controller identity without broad cleanup.
        owner = record.get("container_ownership") or {}
        if owner.get("supervised"):
            verified, detail = _leases_utils.cleanup_exact(
                _leases_models.ContainerIdentity(name=owner["name"], run_id=record["run_id"],
                                                token=owner["launch_token"], docker_endpoint=owner.get("docker_endpoint")))
            owner.update(cleanup_verified=verified, cleanup_detail=detail)
            if not verified:
                record["error_category"] = "container_cleanup_unverified"

    def model_catalog(self, *, refresh=False):
        """Share an in-flight discovery across simultaneous editor refreshes."""
        with self._catalog_lock:
            cached = getattr(self, "_catalog_cached", None)
            if not refresh and cached and time.monotonic() - cached[0] < 300:
                return deepcopy(cached[1])
            pending = getattr(self, "_catalog_pending", None)
            owner = pending is None
            if owner:
                pending = self._catalog_pending = Future()
        if not owner:
            try:
                return deepcopy(pending.result(timeout=65))
            except FutureTimeout:
                raise _runtime_errors.RunnerError(
                    "runner_model_catalog_unavailable_check_runner_connection"
                ) from None
        try:
            result = self._discover_models()
            with self._catalog_lock:
                self._catalog_cached = (time.monotonic(), deepcopy(result))
            pending.set_result(result)
            return deepcopy(result)
        except Exception as exc:
            pending.set_exception(exc)
            raise
        finally:
            with self._catalog_lock:
                self._catalog_pending = None

    def _discover_models(self):
        """The native account picker, using only an initialize control request.

        No user message, session resume, model turn, or transcript is created.
        Bound the entire CLI lifetime below the component's HTTP deadline.
        """
        failure = "runner_model_catalog_unavailable_check_runner_connection"
        self._check_auth(timeout=15)
        try:
            args = [
                "--print",
                "--input-format",
                "stream-json",
                "--output-format",
                "stream-json",
                "--verbose",
                "--no-session-persistence",
                "--tools",
                "",
                "--restricted",
                "--setting-sources",
                "",
                "--strict-mcp-config",
                "--mcp-config",
                '{"mcpServers":{}}',
                "--permission-mode",
                "dontAsk",
                "--permission-prompts",
                "none",
            ]
            request_id = str(uuid4())
            payload = {
                "type": "control_request",
                "request_id": request_id,
                "request": {"subtype": "initialize", "hooks": {}},
            }
            result = self.container.control(
                args, input=(json.dumps(payload) + "\n").encode(), timeout=45
            )
            raw = result.stdout
            if result.exit_code or len(raw) > 1024 * 1024:
                raise ValueError("invalid_catalog_transport")
            responses = []
            for line in raw.decode("utf-8").splitlines():
                event = json.loads(line)
                if (
                    not isinstance(event, dict)
                    or event.get("type") != "control_response"
                ):
                    raise ValueError("unexpected_catalog_event")
                response = event["response"]
                if (
                    not isinstance(response, dict)
                    or response.get("request_id") != request_id
                    or response.get("subtype") != "success"
                ):
                    raise ValueError("catalog_identity_mismatch")
                responses.append(response["response"])
            if len(responses) != 1:
                raise ValueError("catalog_response_missing")
            if not isinstance(responses[0], dict):
                raise ValueError("invalid_catalog_response")
            models = _agents_providers_claude_utils.normalize_models(
                responses[0]["models"]
            )
            return {
                "models": models,
                "provider": "claude",
                "source": "claude_cli_initialize",
                "account_availability": "cli_reported",
                "submitted_turns": 0,
            }
        except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
            raise _runtime_errors.RunnerError(failure) from None

    def __init__(
        self,
        state,
        skill_store,
        source_workspace,
        *,
        image=_claude_settings.IMAGE,
        profile_volume=_claude_settings.PROFILE,
        lease_service=None,
        turn_timeout=180,
        container=None,
        github_authority=None,
        mediator_state=None,
        git_workspace=False,
        artifact_sources=None,
    ):
        if type(turn_timeout) is not int or not 1 <= turn_timeout <= 86400:
            raise _runtime_errors.RunnerError("claude_turn_timeout_invalid")
        self.turn_timeout = turn_timeout
        self.container = container or _claude_container.ClaudeContainer(
            image, profile_volume, lease_service
        )
        self.executable = "claude"
        self._catalog_lock = threading.Lock()
        super().__init__(
            state,
            skill_store,
            source_workspace,
            lease_service=lease_service,
            github_authority=github_authority,
            mediator_state=mediator_state,
            git_workspace=git_workspace,
            artifact_sources=artifact_sources,
        )
        self.profile = self.container.profile
        self.image, self.image_id = image, self.container.image_id

    def _mirror_host_login(self, *, minimum_validity_seconds=None):
        if _host_claude_settings.Settings().mirror_host_login == "1":
            try:
                _host_credentials_claude_utils.mirror_login(
                    self.container.profile,
                    self.container.image_id,
                    minimum_validity_seconds=minimum_validity_seconds
                    or self.turn_timeout,
                )
            except _claude_errors.LocalClaudeLoginError as error:
                if str(error) == "claude_host_login_unavailable":
                    raise _runtime_errors.RunnerError(
                        "claude_host_login_unavailable"
                    ) from None
                if str(error) == "claude_host_login_expired":
                    raise _runtime_errors.RunnerError(
                        "claude_host_login_expired"
                    ) from None
                raise _runtime_errors.RunnerError(
                    "claude_local_login_copy_failed"
                ) from None

    def _check_auth(self, *, timeout=20, minimum_validity_seconds=None):
        self._mirror_host_login(minimum_validity_seconds=minimum_validity_seconds)
        checked = self.container.control(["auth", "status"], timeout=timeout)
        try:
            auth = json.loads(checked.stdout)
        except ValueError:
            raise _runtime_errors.RunnerError(
                "claude_subscription_unavailable"
            ) from None
        if (
            checked.exit_code
            or not auth.get("loggedIn")
            or auth.get("authMethod") != "claude.ai"
        ):
            raise _runtime_errors.RunnerError("claude_subscription_unavailable")
        identity = {key: auth[key] for key in ("email", "orgId") if auth.get(key)}
        return (
            "sha256:"
            + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
            if identity
            else None
        )

    def preflight(self):
        """Check native authentication after constructor image/version validation.

        The existing opt-in login mirror may update the dedicated credential
        volume. This check sends no model request and makes no permission-probe
        claim. Preserve the public ready payload and its authentication meaning.
        """
        self._check_auth()
        return {
            "provider": self.provider,
            "cli_version": _claude_settings.CLI_VERSION,
            "status": "ready",
            "native_tools": ["Skill", "mcp__laomedo__exec_command"],
            "profile": self.profile,
            "image_id": self.image_id,
            "profile_mode": "dedicated_volume",
        }

    def _prepare(self, request, **kwargs):
        if (
            not isinstance(request, dict)
            or not isinstance(request.get("model"), str)
            or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_.\[\]-]{0,159}", request["model"]
            )
        ):
            raise _runtime_errors.RunnerError("claude_model_required")
        if request.get("effort") not in _claude_catalog.EFFORTS:
            raise _runtime_errors.RunnerError("unsupported_claude_effort")
        timeout = request.get("run_timeout_seconds", self.turn_timeout)
        if type(timeout) is not int or not 1 <= timeout <= 86400:
            raise _runtime_errors.RunnerError("claude_turn_timeout_invalid")
        # Explicit editor refresh owns discovery latency. Reuse the last native
        # selection for dispatch even after its editor-cache TTL; never silently
        # remap an alias during a slow concurrent refresh. A cold API client
        # refuses promptly until background discovery or explicit refresh completes.
        with self._catalog_lock:
            cached = getattr(self, "_catalog_cached", None)
            selected_catalog = deepcopy(cached[1]) if cached else None
        if not selected_catalog:
            raise _runtime_errors.RunnerError(
                "runner_model_catalog_unavailable_check_runner_connection"
            )
        choices = selected_catalog["models"]
        choice = next(
            (item for item in choices if item["id"] == request["model"]), None
        )
        if choice is None:
            choice = next(
                (
                    item
                    for item in choices
                    if item["resolved_model"] == request["model"]
                ),
                None,
            )
        if choice is None:
            raise _runtime_errors.RunnerError("claude_model_required")
        if request["effort"] not in choice["efforts"]:
            raise _runtime_errors.RunnerError("unsupported_claude_effort")
        # Pinned native skills may instruct draft commands through the isolated
        # worker, but may not execute shell substitutions/hooks in the credential
        # controller or widen its frozen tools/model/session grant.
        references = request.get(
            "skill_refs", [request["skill_ref"]] if "skill_ref" in request else []
        )
        if isinstance(references, list) and len(references) <= 16:
            for ref in references:
                if (
                    not isinstance(ref, dict)
                    or not isinstance(ref.get("skill_id"), str)
                    or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", ref["skill_id"])
                    or not isinstance(ref.get("revision_id"), str)
                    or not re.fullmatch(r"sha256:[0-9a-f]{64}", ref["revision_id"])
                ):
                    continue  # The shared validator supplies the stable input error.
                bundle = self.store.revision(ref["skill_id"], ref["revision_id"])
                for path in bundle["file_hashes"]:
                    if Path(path).name != "SKILL.md":
                        continue
                    try:
                        text = (
                            self.store.read_file(
                                ref["skill_id"], ref["revision_id"], path
                            )["content"]
                            .decode("utf-8-sig")
                            .replace("\r\n", "\n")
                            .replace("\r", "\n")
                        )
                    except UnicodeError:
                        raise _runtime_errors.RunnerError(
                            "skill_frontmatter_name_required"
                        ) from None
                    if re.search(r"!`", text):
                        raise _runtime_errors.RunnerError(
                            "claude_native_skill_policy_unsupported"
                        )
                    # Reject ambiguous delimiters rather than guessing how the
                    # native loader interprets whitespace or unterminated YAML.
                    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
                        raise _runtime_errors.RunnerError(
                            "claude_native_skill_policy_unsupported"
                        )
                    front = text[4:].split("\n---\n", 1)[0]
                    allowed = {
                        "name",
                        "description",
                        "license",
                        "compatibility",
                        "metadata",
                        "argument-hint",
                        "user-invocable",
                        "disable-model-invocation",
                    }
                    for line in front.splitlines():
                        if (
                            not line.strip()
                            or line.lstrip().startswith("#")
                            or line[0].isspace()
                        ):
                            continue
                        key = re.match(r"^['\"]?([A-Za-z0-9_-]+)['\"]?\s*:", line)
                        if key is None or key.group(1) not in allowed:
                            raise _runtime_errors.RunnerError(
                                "claude_native_skill_policy_unsupported"
                            )
        record = super()._prepare(request, **kwargs)
        record.update(
            provider=self.provider,
            runtime_version=_claude_settings.CLI_VERSION,
            execution_mode="claude_container",
            profile=self.profile,
            image=self.image,
            image_id=self.image_id,
            cli_version="Claude Code " + _claude_settings.CLI_VERSION,
            config_sha256=_agents_providers_claude_utils.configuration_hash(
                choice["resolved_model"], request["effort"], record["skills"]
            ),
            native_tools=(["Skill"] if record["skills"] else [])
            + ["mcp__laomedo__exec_command"],
            turn_timeout=timeout,
            resolved_model=choice["resolved_model"],
            permission_grant={
                "workspace": "draft-write",
                "commands": "network-free-worker",
                "profile": "controller-only",
                "external_effects": "host-mediated",
            },
        )
        _runtime_utils._json(self._run_dir(record["run_id"]) / "record.json", record)
        return record

    def _verify_skills(self, root, record):
        for skill in record["skills"]:
            path = root / "workspace/.agents/skills" / skill["skill_id"]
            if (
                _registry_utils.tree_hash(_registry_utils.inventory(path))
                != skill["tree_hash"]
            ):
                raise _runtime_errors.RunnerError("pinned_skill_workspace_changed")
        workspace_skills.verify(
            root / "workspace", record["skills"], record["skill_git_exclusion"]
        )
        if (
            _runtime_utils._hash_tree(root / "canonical") != record["source_hash"]
            or (root / "store/sentinel.txt").read_text(encoding="utf-8")
            != "STORE-ORIGINAL"
        ):
            raise _runtime_errors.RunnerError("protected_mount_changed")

    def _prompt(self, root, record, task):
        # Skills are native CLI plugin bundles, never text-truncated snapshots.
        for skill in record["skills"]:
            skill.update(delivery_mode="native_plugin")
            skill.setdefault("use_evidence", "offered")
        record["skill"] = (
            deepcopy(record["skills"][0]) if len(record["skills"]) == 1 else None
        )
        return json.dumps(
            {
                "task": task,
                "workspace": "/draft",
                "skills": [
                    {"skill_id": x["skill_id"], "revision_id": x["revision_id"]}
                    for x in record["skills"]
                ],
                "imported_artifacts": record.get("imported_artifacts", []),
                "output_requirements": record.get("output_requirements"),
            },
            ensure_ascii=False,
        )

    def _invoke(self, root, record, prompt, flag, *, resume):
        name, token = "laomedo-claude-" + uuid4().hex, uuid4().hex
        record["container_ownership"] = {
            "name": name,
            "docker_endpoint": getattr(self.container, "docker_endpoint", None),
            "launch_token": token,
            "supervised": True,
            "cleanup_verified": False,
        }
        _runtime_utils._json(root / "record.json", record)
        lease = self.container.lease(
            record["run_id"], name, token, flag, record.get("github_scope")
        )
        deadline = record.get(
            "_attempt_deadline", time.monotonic() + record["turn_timeout"]
        )
        service, telemetry, watcher, session = None, None, None, None
        watch_stop = threading.Event()
        input_path = root.joinpath("controller-input-" + uuid4().hex)
        native_completed = False
        output_only = record.get("output_correction_count", 0) > 0
        try:
            plugin = root / "native-skill-plugin"
            (plugin / ".claude-plugin").mkdir(parents=True, exist_ok=True)
            _runtime_utils._json(
                plugin / ".claude-plugin/plugin.json",
                {"name": "laomedo-pinned", "version": "1.0.0"},
            )
            (plugin / "skills").mkdir(exist_ok=True)
            (root / "workspace/.claude/skills").mkdir(parents=True, exist_ok=True)
            mediation = None
            if record.get("github_scope"):
                if lease.grant_id is None:
                    raise _runtime_errors.RunnerError("mediated_grant_unavailable")
                route, instance = self._mediator_route()
                mediation = (route, instance, lease.dir / "grant.secret")
            service = _claude_container.CommandService(
                self.container, root, record, flag, deadline, mediation=mediation
            )
            try:
                import laomedo.activity.claude.telemetry as _claude_telemetry

                telemetry = _claude_telemetry.ClaudeTelemetry(
                    root,
                    run_id=record["run_id"],
                    thread_id=record["thread_id"],
                    turn_id=record["active_host_turn"],
                )
            except (ImportError, OSError):
                raise _runtime_errors.RunnerError(
                    "claude_telemetry_start_failed"
                ) from None
            native = _agents_providers_claude_utils.command(
                None,
                record.get("resolved_model", record["requested_model"]),
                record["requested_effort"],
                record["thread_id"],
                resume=resume,
                output_only=output_only,
                skill_ids=tuple(x["skill_id"] for x in record["skills"]),
            )
            from py_docker.containers.models import Mount

            input_path.write_bytes(prompt.encode())
            input_path.chmod(0o600)
            command = ["sh", "-c", 'exec "$@" < /run/laomedo/input', "sh", *native]
            spec = self.container.spec(
                self.container.guarded(command, deadline),
                name=name,
                run_id=record["run_id"],
                token=token,
                workspace=root.joinpath("workspace"),
                environment={
                    **telemetry.environment,
                    "LAOMEDO_COMMAND_URL": service.url,
                    "LAOMEDO_GITHUB_GRANTED": "1" if mediation else "0",
                },
                extra_hosts={"host.docker.internal": "host-gateway"},
                mounts=[
                    Mount(
                        type="bind", source=str(source), target=target, read_only=True
                    )
                    for source, target in (
                        (input_path, "/run/laomedo/input"),
                        (plugin, "/run/laomedo/pinned-skills"),
                        (
                            root.joinpath("workspace/.agents/skills"),
                            "/run/laomedo/pinned-skills/skills",
                        ),
                        (service.secret_path, "/run/laomedo/command-token"),
                    )
                ],
            )
            with self.control_lock:
                if flag.is_set():
                    raise _runtime_errors.RunnerError("claude_cancelled")
                if time.monotonic() >= deadline:
                    raise _runtime_errors.RunnerError("claude_turn_timeout")
            with self.container.session(
                spec,
                self.container.receipts.joinpath("claude-" + name + ".json"),
                max(1, deadline - time.monotonic()) + 10,
            ) as session:

                def stop_when_requested():
                    """Terminate the exact owned ID; creator-thread close owns the receipt."""
                    while not watch_stop.wait(0.1):
                        if (
                            flag.is_set()
                            or time.monotonic() >= deadline
                            or service.error_code
                        ):
                            try:
                                session.terminate()
                            except Exception:
                                pass  # Creator close and the independent lease must verify cleanup.
                            return

                watcher = threading.Thread(target=stop_when_requested, daemon=True)
                watcher.start()
                total, stderr_size, result = 0, 0, None
                while True:
                    if flag.is_set():
                        raise _runtime_errors.RunnerError("claude_cancelled")
                    if time.monotonic() >= deadline:
                        raise _runtime_errors.RunnerError("claude_turn_timeout")
                    line = session.read_line()
                    if line is None:
                        break
                    if line.channel == "stderr":
                        stderr_size += len(line.data)
                        if stderr_size > 4 * 1024 * 1024:
                            raise _runtime_errors.RunnerError(
                                "claude_receipt_too_large"
                            )
                        continue
                    line = line.data
                    total += len(line)
                    if len(line) > 1024 * 1024 or total > 32 * 1024 * 1024:
                        raise _runtime_errors.RunnerError("claude_receipt_too_large")
                    try:
                        event = json.loads(line)
                    except ValueError:
                        raise _runtime_errors.RunnerError(
                            "claude_terminal_receipt_invalid"
                        ) from None
                    self._native_event(root, record, event)
                    if event.get("type") == "result":
                        if result is not None:
                            raise _runtime_errors.RunnerError(
                                "claude_terminal_receipt_invalid"
                            )
                        result = event
                exit_code = session.wait(timeout=10)
                if exit_code == 124:
                    raise _runtime_errors.RunnerError("claude_turn_timeout")
                if exit_code or result is None:
                    raise _runtime_errors.RunnerError("claude_native_turn_failed")
                completed = _agents_providers_claude_utils.terminal_result(
                    json.dumps(result), record["thread_id"]
                )
                native_completed = True
                return completed
        finally:
            service_error = False
            if service is not None:
                try:
                    service.close()
                except Exception:
                    service_error = True
            watch_stop.set()
            verified, detail = True, "removed"
            if session is not None and session.cleanup_confirmed is not True:
                verified, detail = False, "sdk_cleanup_unverified"
            elif session is None:
                verified, detail = _leases_utils.cleanup_exact(
                    _leases_models.ContainerIdentity(
                        name=name,
                        run_id=record["run_id"],
                        token=token,
                        docker_endpoint=getattr(
                            self.container, "docker_endpoint", None
                        ),
                    )
                )
            if self.container.receipts.joinpath("claude-" + name + ".json").exists():
                verified, detail = False, "pending_sdk_receipt"
            if watcher is not None:
                watcher.join(3)
                verified = verified and not watcher.is_alive()
            input_path.unlink(missing_ok=True)
            if verified:
                try:
                    lease.finish()
                except RuntimeError:
                    verified = False
            else:
                # Do not mark an unknown owner done: its independent lease must
                # take the loss-cleanup path, in addition to the kernel deadline.
                lease.stop_heartbeats()
            verified = verified and not service_error
            record["container_ownership"].update(
                cleanup_verified=verified, cleanup_detail=detail
            )
            record["descendant_cleanup"] = "verified" if verified else "not_verified"
            _runtime_utils._json(root / "record.json", record)
            telemetry_cleanup_failed = False
            if telemetry is not None:
                try:
                    telemetry.close()
                except Exception:
                    telemetry_cleanup_failed = True
            if not verified:
                raise _runtime_errors.RunnerError("container_termination_unverified")
            if telemetry is not None:
                capture = record.setdefault(
                    "telemetry_capture",
                    {
                        "records": 0,
                        "receiver_error": False,
                        "flush_completeness": "unverified",
                    },
                )
                capture["records"] += telemetry.count
                capture["receiver_error"] = (
                    capture["receiver_error"] or telemetry.failed
                )
                if telemetry_cleanup_failed:
                    capture["error_category"] = "claude_telemetry_cleanup_unconfirmed"
                elif telemetry.failed or (native_completed and telemetry.count == 0):
                    capture.setdefault(
                        "error_category", "claude_telemetry_capture_failed"
                    )
                # Capture failure must not discard an attested native result or
                # its completed snapshot, or invite replay of effects already done.
            if service is not None and service.error_code:
                raise _runtime_errors.RunnerError("workspace_command_output_too_large")
            if not native_completed and flag.is_set():
                raise _runtime_errors.RunnerError("claude_cancelled")
            if not native_completed and time.monotonic() >= deadline:
                raise _runtime_errors.RunnerError("claude_turn_timeout")

    def _native_event(self, root, record, event):
        if (
            not isinstance(event, dict)
            or event.get("session_id", record["thread_id"]) != record["thread_id"]
        ):
            raise _runtime_errors.RunnerError("claude_session_identity_mismatch")
        with (root / "raw-events.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps(_runner_feed.receipt(event)) + "\n")
        turn = record.get("active_host_turn")
        common = {"threadId": record["thread_id"], "turnId": turn}
        if event.get("type") == "system" and event.get("subtype") == "init":
            record["native_initialization"] = {
                key: event.get(key)
                for key in ("model", "tools", "skills", "permissionMode")
            }
            record["effective_model"] = event.get("model")
            record["effective_effort"] = event.get("effort")
            record["configured_effort"] = record["requested_effort"]
            record["effective_effort_source"] = (
                "native_initialize" if event.get("effort") else "not_reported"
            )
        content = (event.get("message") or {}).get("content", [])
        tools = record.setdefault("_native_tool_calls", {})
        for index, block in enumerate(content if isinstance(content, list) else []):
            if not isinstance(block, dict):
                raise _runtime_errors.RunnerError("claude_terminal_receipt_invalid")
            if block.get("type") == "tool_use":
                item = {
                    "id": block["id"],
                    "type": "dynamicToolCall",
                    "tool": block.get("name"),
                    "arguments": block.get("input"),
                    "status": "running",
                }
                tools[block["id"]] = item
                self._event(root, "item/started", {**common, "item": item})
            elif block.get("type") == "tool_result":
                identity = block.get("tool_use_id")
                item = tools.pop(identity, {"id": identity, "type": "dynamicToolCall"})
                item = {
                    **item,
                    "status": "failed" if block.get("is_error") else "completed",
                    "output": block.get("content"),
                    "isError": block.get("is_error", False),
                }
                self._event(root, "item/completed", {**common, "item": item})
                if item.get("tool") == "Skill" and not item["isError"]:
                    selected = (item.get("arguments") or {}).get("skill", "")
                    for skill in record["skills"]:
                        if selected in {
                            skill["skill_id"],
                            "laomedo-pinned:" + skill["skill_id"],
                        }:
                            skill["use_evidence"] = "native_skill_tool_completed"
                    record["skill"] = (
                        deepcopy(record["skills"][0])
                        if len(record["skills"]) == 1
                        else None
                    )
            elif block.get("type") in {"text", "thinking"}:
                text = block.get("text", block.get("thinking", ""))
                if block["type"] == "text":
                    record["_last_streamed_text"] = text
                message_id = str(
                    (event.get("message") or {}).get("id", event.get("uuid", turn))
                )
                kind = "reasoning" if block["type"] == "thinking" else "agentMessage"
                digest = hashlib.sha256(text.encode()).hexdigest()
                prior = [
                    item
                    for item in record.get("_completed_stream_items", {}).values()
                    if item["message_id"] == message_id and item["type"] == kind
                ]
                if any(item["text_hash"] == digest for item in prior):
                    continue  # Raw native receipts remain intact; don't duplicate the display.
                # Native assistant receipts can precede content_block_stop. Reuse
                # the open block's identity too; its index need not match the
                # receipt's single-block content index (e.g. thinking then text).
                active = [
                    item
                    for item in record.get("_stream_blocks", {}).values()
                    if record.get("_stream_message_id") == message_id
                    and item["type"] == kind
                ]
                matching = [
                    item
                    for item in active
                    if hashlib.sha256(item["text"].encode()).hexdigest() == digest
                ]
                candidates = matching or active or prior
                identity = (
                    candidates[0]["id"]
                    if len(candidates) == 1
                    else message_id + ":native:" + kind + ":" + str(index)
                )
                self._event(
                    root,
                    "item/completed",
                    {**common, "item": {"id": identity, "type": kind, "text": text}},
                )
        partial = event.get("event") if event.get("type") == "stream_event" else None
        if isinstance(partial, dict):
            kind = partial.get("type")
            if kind == "message_start":
                record["_stream_message_id"] = (partial.get("message") or {}).get(
                    "id", str(uuid4())
                )
                record["_stream_blocks"] = {}
            blocks = record.setdefault("_stream_blocks", {})
            index = str(partial.get("index", 0))
            if kind == "content_block_start":
                block = partial.get("content_block") or {}
                if block.get("type") in {"text", "thinking"}:
                    blocks[index] = {
                        "id": record.get("_stream_message_id", turn) + ":" + index,
                        "type": (
                            "reasoning"
                            if block["type"] == "thinking"
                            else "agentMessage"
                        ),
                        "text": block.get("text", block.get("thinking", "")),
                    }
                    self._event(
                        root, "item/started", {**common, "item": dict(blocks[index])}
                    )
            elif kind == "content_block_delta" and index in blocks:
                delta = partial.get("delta") or {}
                blocks[index]["text"] += delta.get("text", delta.get("thinking", ""))
                self._event(
                    root, "item/updated", {**common, "item": dict(blocks[index])}
                )
            elif kind == "content_block_stop" and index in blocks:
                completed = blocks.pop(index)
                record.setdefault("_completed_stream_items", {})[completed["id"]] = {
                    "id": completed["id"],
                    "message_id": record.get("_stream_message_id", turn),
                    "type": completed["type"],
                    "text_hash": hashlib.sha256(completed["text"].encode()).hexdigest(),
                }
                if completed["type"] == "agentMessage":
                    record["_last_streamed_text"] = completed["text"]
                self._event(root, "item/completed", {**common, "item": completed})
            elif kind == "message_stop":
                record["_stream_blocks"] = {}

    def _event(self, root, method, params):
        # These are explicitly adapter-normalized receipts, not Codex RPC events.
        event = {
            "method": method,
            "params": params,
            "provider": "claude",
            "normalization": "claude-stream-v3",
        }
        with (root / "activity-events.jsonl").open("a", encoding="utf-8") as output:
            output.write(json.dumps(_runner_feed.receipt(event)) + "\n")

    def _execute(
        self,
        run_id,
        task,
        *,
        resume,
        activity_attempt_id=None,
        run_timeout_seconds=None,
    ):
        if not self.lock.acquire(blocking=False):
            raise _runtime_errors.RunnerError("runner_busy")
        record, attempt, flag = None, None, threading.Event()
        try:
            root = self._run_dir(run_id)
            with self.control_lock:
                candidate = self.status(run_id)
                if candidate["status"] == "cancelled" and candidate.get(
                    "cancel_confirmed"
                ):
                    return candidate
                if candidate["status"] != ("completed" if resume else "prepared"):
                    raise _runtime_errors.RunnerError("run_not_dispatchable")
                record = candidate
                if run_timeout_seconds is not None:
                    record["turn_timeout"] = run_timeout_seconds
                self.cancel_flags[run_id] = flag
                record.update(
                    status="running",
                    attempt_finished=False,
                    snapshot_ready=False,
                    evidence_complete="unknown",
                    completion_basis=None,
                )
                record["_attempt_deadline"] = time.monotonic() + record["turn_timeout"]
                _runtime_utils._json(root / "record.json", record)
            self._verify_skills(root, record)
            remaining = record["_attempt_deadline"] - time.monotonic()
            if remaining <= 0:
                raise _runtime_errors.RunnerError("claude_turn_timeout")
            identity = self._check_auth(
                timeout=min(60, remaining), minimum_validity_seconds=remaining
            )
            if resume and (
                not identity or record.get("credential_subject_hash") != identity
            ):
                raise _runtime_errors.RunnerError("resume_auth_identity_mismatch")
            record["credential_subject_hash"] = identity
            if not resume:
                record["thread_id"] = str(uuid4())
            attempt_id = (
                activity_attempt_id if resume else record["activity_initial_attempt_id"]
            )
            attempt_id = attempt_id or str(uuid4())
            UUID(attempt_id)
            folder = root / "activity-attempts"
            folder.mkdir(exist_ok=True)
            if (folder / (attempt_id + ".json")).exists():
                raise _runtime_errors.RunnerError("activity_attempt_already_exists")
            baseline = (
                _agents_providers_claude_utils.activity_usage(
                    {"modelUsage": record.get("native_model_usage")}
                )
                if resume
                else {}
            )
            record["telemetry_capture"] = {
                "records": 0,
                "receiver_error": False,
                "flush_completeness": "unverified",
            }
            attempt = {
                "id": attempt_id,
                "native_start": _runner_feed.line_count(root / "activity-events.jsonl"),
                "otel_start": _runner_feed.line_count(root / "otel-events.jsonl"),
                "usage_baseline": (
                    {record["thread_id"]: {"total": baseline}} if resume else {}
                ),
                "native_end": None,
                "fresh_thread": not resume,
                "otel_end": None,
                "status": "running",
                "ended_at": None,
            }
            _runtime_utils._json(folder / (attempt_id + ".json"), attempt)
            record["activity_attempt_id"] = attempt_id
            self._event(root, "thread/started", {"thread": {"id": record["thread_id"]}})
            prompt = self._prompt(root, record, task)
            corrections = 0
            while True:
                if flag.is_set():
                    raise _runtime_errors.RunnerError("claude_cancelled")
                record["attempt_number"] = self._reserve_turn()
                _runtime_utils._json(root / "record.json", record)
                host_turn = str(uuid4())
                record.pop("_last_streamed_text", None)
                record["_completed_stream_items"] = {}
                record["active_host_turn"] = host_turn
                record["output_correction_count"] = corrections
                self._event(
                    root,
                    "turn/started",
                    {
                        "threadId": record["thread_id"],
                        "turn": {"id": host_turn},
                        "identity_source": "host_attempt",
                    },
                )
                self._event(
                    root,
                    "item/completed",
                    {
                        "threadId": record["thread_id"],
                        "turnId": host_turn,
                        "item": {
                            "id": host_turn + ":prompt",
                            "type": "userMessage",
                            "content": [{"type": "inputText", "text": prompt}],
                            "provenance": "host_submitted_prompt",
                        },
                    },
                )
                try:
                    result = self._invoke(
                        root, record, prompt, flag, resume=resume or corrections > 0
                    )
                except Exception:
                    self._event(
                        root,
                        "thread/tokenUsage/updated",
                        {
                            "threadId": record["thread_id"],
                            "turnId": host_turn,
                            "tokenUsage": {"total": None},
                            "usage_scope": "terminal_receipt_unavailable",
                        },
                    )
                    self._event(
                        root,
                        "turn/completed",
                        {
                            "threadId": record["thread_id"],
                            "turn": {
                                "id": host_turn,
                                "status": "cancelled" if flag.is_set() else "failed",
                            },
                            "identity_source": "host_attempt",
                        },
                    )
                    raise
                totals = _agents_providers_claude_utils.activity_usage(result)
                # Explicitly invalidate unknown resume baselines instead of charging
                # the entire session to the latest invocation.
                if resume and baseline is None:
                    totals = None
                elif (
                    resume
                    and totals is not None
                    and "reasoningOutputTokens" not in baseline
                ):
                    totals.pop("reasoningOutputTokens", None)
                self._event(
                    root,
                    "thread/tokenUsage/updated",
                    {
                        "threadId": record["thread_id"],
                        "turnId": host_turn,
                        "tokenUsage": {"total": totals},
                        "usage_scope": "native_session_cumulative",
                    },
                )
                self._event(
                    root,
                    "claude/result",
                    {
                        "threadId": record["thread_id"],
                        "turnId": host_turn,
                        "subtype": result.get("subtype"),
                        "duration_ms": result.get("duration_ms"),
                        "duration_api_ms": result.get("duration_api_ms"),
                        "native_session_id": result["session_id"],
                        "tools_enabled": corrections == 0,
                        "reported_models": (
                            list(result.get("modelUsage", {}))
                            if isinstance(result.get("modelUsage"), dict)
                            else []
                        ),
                        "evidence": "native_stream_and_receipt",
                        "usage_scope": "native_session_cumulative",
                        "reported_session_cost_usd": result.get("total_cost_usd"),
                        "cost_basis": "CLI estimate; cumulative session, not a subscription charge",
                    },
                )
                answer = result["result"]
                turn = {
                    "turn_id": host_turn,
                    "identity_source": "host_attempt",
                    "status": "completed",
                    "execution_timeout_seconds": record["turn_timeout"],
                    "input_hash": "sha256:"
                    + hashlib.sha256(prompt.encode()).hexdigest(),
                    "native_session_id": result["session_id"],
                }
                record["turns"].append(turn)
                if str(record.get("_last_streamed_text", "")).strip() != answer.strip():
                    self._event(
                        root,
                        "item/completed",
                        {
                            "threadId": record["thread_id"],
                            "turnId": host_turn,
                            "item": {
                                "id": host_turn + ":answer",
                                "type": "agentMessage",
                                "text": answer,
                            },
                        },
                    )
                self._event(
                    root,
                    "turn/completed",
                    {
                        "threadId": record["thread_id"],
                        "turn": {"id": host_turn, "status": "completed"},
                        "native_session_id": result["session_id"],
                    },
                )
                record.update(
                    answer=answer,
                    native_answer=answer,
                    usage=result.get("usage"),
                    native_model_usage=result.get("modelUsage"),
                    output_correction_count=corrections,
                    precheck={"installed": False, "call_count": 0},
                )
                models = result.get("modelUsage")
                record["effective_model"] = (
                    next(iter(models))
                    if isinstance(models, dict)
                    and len(models) == 1
                    and all(isinstance(key, str) for key in models)
                    else None
                )
                requirements = record.get("output_requirements")
                if not requirements:
                    break
                try:
                    submission = json.loads(answer)
                except ValueError as exc:
                    submission = None
                    parse_error = (
                        "trailing_data"
                        if isinstance(exc, json.JSONDecodeError)
                        and exc.msg == "Extra data"
                        else "invalid_json"
                    )
                else:
                    parse_error = None
                validation = _contracts_output.evaluate(requirements, submission)
                if parse_error:
                    validation.update(
                        contract_status="rejected",
                        errors=[{"path": "", "code": parse_error}],
                    )
                record["output_validation"] = validation
                turn["output_validation"] = validation
                if (
                    validation["contract_status"] == "accepted"
                    or corrections >= record["output_retries"]
                ):
                    break
                self._turn_available()
                prompt = json.dumps(
                    {
                        "instruction": "Correct only the previous output. Return one JSON object, no fences or trailing characters. Do not repeat any action.",
                        "validation": validation,
                        "requirements": requirements,
                    }
                )
                corrections += 1
            if flag.is_set():
                raise _runtime_errors.RunnerError("claude_cancelled")
            self._verify_skills(root, record)
            if _runtime_utils._hash_tree(root / "canonical") != record["source_hash"]:
                raise _runtime_errors.RunnerError("protected_mount_changed")
            snapshot = root / "post-run-pending"
            digest = _runtime_utils._copy_tree(root / "workspace", snapshot)
            if (root / "post-run").exists():
                workspace_skills.remove_owned_tree(root / "post-run", self.state)
            snapshot.rename(root / "post-run")
            record.update(
                status="completed",
                post_run_hash=digest,
                snapshot_ready=True,
                output_ref=f"laomedo:run:{run_id}:workspace",
                evidence_complete="unknown",
                completion_basis="claude_native_stream_and_receipt",
            )
        except Exception as exc:
            if record is None:
                raise
            record.update(
                status="cancelled" if flag.is_set() else "failed",
                error_category=(
                    "claude_mediation_outcome_unknown"
                    if record.get("mediation_outcome") == "unknown"
                    else (
                        str(exc)
                        if isinstance(exc, _runtime_errors.RunnerError)
                        else type(exc).__name__
                    )
                ),
                snapshot_ready=False,
                evidence_complete="unknown",
                completion_basis=None,
                post_run_hash=None,
                output_ref=None,
            )
        finally:
            if record is not None:
                record["cancel_confirmed"] = bool(
                    flag.is_set()
                    and record.get("container_ownership", {}).get("cleanup_verified")
                    is True
                    and record.get("descendant_cleanup") == "verified"
                    and record.get("mediation_outcome") != "unknown"
                )
                record.pop("_attempt_deadline", None)
                record.update(attempt_finished=True, cancel_requested=flag.is_set())
                if attempt is not None:
                    attempt.update(
                        native_end=_runner_feed.line_count(
                            self._run_dir(run_id) / "activity-events.jsonl"
                        ),
                        otel_end=_runner_feed.line_count(
                            self._run_dir(run_id) / "otel-events.jsonl"
                        ),
                        status=record["status"],
                        ended_at=_agent_activity_utils.now(),
                        capture_error=record.get("telemetry_capture", {}).get(
                            "error_category"
                        ),
                    )
                    _runtime_utils._json(
                        self._run_dir(run_id)
                        / "activity-attempts"
                        / (attempt["id"] + ".json"),
                        attempt,
                    )
                _runtime_utils._json(self._run_dir(run_id) / "record.json", record)
            self.cancel_flags.pop(run_id, None)
            self.lock.release()
        return record

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
        run_timeout_seconds=None,
    ):
        if run_timeout_seconds is not None and (
            type(run_timeout_seconds) is not int
            or not 1 <= run_timeout_seconds <= 86400
        ):
            raise _runtime_errors.RunnerError("claude_turn_timeout_invalid")
        record = self.status(run_id)
        root = self._run_dir(run_id)
        if (
            record.get("provider") != self.provider
            or record.get("runtime_version") != _claude_settings.CLI_VERSION
            or record.get("image_id") != self.image_id
            or record.get("profile") != self.profile
            or record.get("config_sha256")
            != _agents_providers_claude_utils.configuration_hash(
                record.get("resolved_model"), effort, record.get("skills", [])
            )
            or record.get("permission_grant")
            != {
                "workspace": "draft-write",
                "commands": "network-free-worker",
                "profile": "controller-only",
                "external_effects": "host-mediated",
            }
            or record.get("execution_mode") != "claude_container"
            or record["status"] != "completed"
            or record["thread_id"] != expected_thread_id
            or record["post_run_hash"] != expected_post_run_hash
            or record["requested_model"] != model
            or record["requested_effort"] != effort
            or not isinstance(task, str)
            or not task.strip()
        ):
            raise _runtime_errors.RunnerError("resume_binding_mismatch")
        if (
            not (root / "post-run").is_dir()
            or _runtime_utils._hash_tree(root / "post-run") != expected_post_run_hash
        ):
            raise _runtime_errors.RunnerError("post_run_snapshot_mismatch")
        if _runtime_utils._hash_tree(root / "workspace") != expected_post_run_hash:
            raise _runtime_errors.RunnerError("workspace_changed_since_snapshot")
        return self._execute(
            run_id,
            task,
            resume=True,
            activity_attempt_id=activity_attempt_id,
            run_timeout_seconds=run_timeout_seconds,
        )

    def cancel(self, run_id):
        with self.control_lock:
            record = self.status(run_id)
            if record["status"] == "prepared":
                record.update(
                    status="cancelled",
                    cancel_requested=True,
                    cancel_confirmed=True,
                    attempt_finished=True,
                )
                _runtime_utils._json(self._run_dir(run_id) / "record.json", record)
                return record
        if record["status"] == "running":
            flag = self.cancel_flags.get(run_id)
            if flag is None:
                raise _runtime_errors.RunnerError("run_not_active_in_this_process")
            with self.control_lock:
                flag.set()
            # The execution loop owns teardown of both controller and workers.
            # Concurrent removals here race its finally block and can report a
            # spurious failure even though exact cleanup subsequently succeeds.
            # Acknowledge the request only; terminal status confirms cleanup.
            return {**record, "cancel_requested": True, "cancel_confirmed": False}
        return record
