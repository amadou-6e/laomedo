"""Codex launch policy and native evidence over the shared ACP client."""

import asyncio
from contextlib import ExitStack
import json
import time

from laomedo.agents.interface.output.utils import dynamic_tool
from laomedo.agents.interface.output.utils import precheck_response
from laomedo.agents.interface.output.utils import verify_requirements
from laomedo.agents.agents.codex.settings import NATIVE_RECEIPT_FILENAME
from laomedo.agents.agents.codex.settings import Settings as CodexSettings
from laomedo.agents.agents.codex.controller.models import CodexLaunch
from laomedo.agents.agents.codex.controller.models import CodexTurn
from laomedo.agents.agents.codex.controller.models import CodexCommandResult
from laomedo.agents.agents.codex.commands import CodexCommands
from laomedo.agents.agents.codex.controller.settings import Settings
from laomedo.agents.errors import RunnerError
from laomedo.docker import DockerRuntime
from laomedo.agents.agents.base.models import CommandRequest
from laomedo.agents.agents.base.models import ProcessHealthObservation
from laomedo.agents.agents.base.models import IsolationObservation
from laomedo.agents.agents.base.utils import failure_observation


class CodexAgentRuntime:
    """Own a controller and optional executor without implementing another wire.

    Native events remain the authority for item identities and terminal status.
    ACP updates are transport receipts, not a second activity projection.
    """

    def __init__(
        self,
        launch: CodexLaunch,
        evidence,
        *,
        env=None,
        secret_redactions=(),
        lifetime_seconds=60,
        receipt_path=None,
        split=None,
    ):
        """Bind admitted configuration and owned state; provider startup errors propagate before use."""
        from py_docker.connection.settings import ConnectionSettings
        from py_docker.sessions.models import ContainerSession
        from py_docker.streams.models import StreamLimits

        self.client = DockerRuntime(
            settings=ConnectionSettings(timeout_seconds=15), environment=env
        ).connect()
        self.container_name = launch.name
        self._session_scope = ExitStack()
        self.session = self.acp = self.executor = self.telemetry = None
        self.native_commands_supported = False
        self.credential_refresh_supported = False
        self.managed_credential = bool(split is not None and split.managed_credential)
        self._cancelled = None
        self._protocol_ready = False
        self.events = []
        self.output_requirements = None
        self.active_thread_id = None
        self.precheck_call_count = 0
        self.verified_precheck_calls = set()
        self.native_completion_status = None
        self.interrupt_acknowledged = False
        self.authorization_probe = None
        self.authorization_failure = {}
        self.cleanup_confirmed = self.streams_closed = False
        self._closed = False
        self._close_failure = None
        self.secret_redactions = tuple(value for value in secret_redactions if value)
        self.logs = []
        try:
            if split is not None:
                from laomedo.agents.agents.codex.split.executor import (
                    CodexCommandExecutor,
                )
                from laomedo.agents.agents.codex.split.models import SplitLaunch

                self.executor = CodexCommandExecutor(
                    launch,
                    evidence,
                    environment=env,
                    lifetime_seconds=lifetime_seconds,
                    receipt_path=receipt_path,
                )
                launch = SplitLaunch(
                    **{
                        name: getattr(launch, name) for name in CodexLaunch.model_fields
                    },
                    executor_id=self.executor.session.identity.id,
                    provider_config=split.provider_config,
                    access_token=split.access_token,
                )
                self.secret_redactions += (self.executor.token,)
                if split.access_token is not None:
                    self.secret_redactions += (split.access_token.get_secret_value(),)
            spec = launch.to_container_spec()
            environment = dict(spec.environment)
            if split is not None and split.managed_credential:
                from pydantic import SecretStr

                environment["LAOMEDO_CODEX_REFRESHABLE_AUTH"] = SecretStr("1")
            arguments = (
                json.loads(environment["LAOMEDO_CODEX_ARGS"].get_secret_value())
                if "LAOMEDO_CODEX_ARGS" in environment
                else []
            )
            if CodexSettings().multi_agent == "1":
                arguments += [
                    "--disable",
                    "memories",
                    "-c",
                    "features.multi_agent=true",
                    "-c",
                    "agents.max_threads=2",
                    "-c",
                    "agents.max_depth=1",
                ]
            from laomedo.agents.activity.runner.settings import (
                Settings as ActivitySettings,
            )

            if ActivitySettings().otel == "1":
                from laomedo.agents.activity.runner.telemetry import LaunchTelemetry

                self.telemetry = LaunchTelemetry(evidence)
                arguments += self.telemetry.arguments()
                self.secret_redactions += (self.telemetry.token,)
            from pydantic import SecretStr

            environment["LAOMEDO_CODEX_ARGS"] = SecretStr(json.dumps(arguments))
            private_tmpfs = dict(spec.tmpfs)
            if self.managed_credential:
                private_tmpfs["/tmp/laomedo-provider-auth"] = (
                    "rw,noexec,nosuid,size=1m,mode=0700,uid=10001,gid=10001"
                )
            spec = spec.model_copy(
                update={"environment": environment, "tmpfs": private_tmpfs}
            )
            self.raw_log = (evidence / "raw-events.jsonl").open("a", encoding="utf-8")
            self.logs.append(self.raw_log)
            self.activity_log = (evidence / "activity-events.jsonl").open(
                "a", encoding="utf-8"
            )
            self.logs.append(self.activity_log)
            self.session = self._session_scope.enter_context(
                DockerRuntime.session(
                    self.client,
                    ContainerSession(
                        spec=spec,
                        limits=StreamLimits(
                            seconds=lifetime_seconds,
                            max_bytes=Settings.load().max_bytes,
                        ),
                        receipt_path=receipt_path or evidence / NATIVE_RECEIPT_FILENAME,
                    ),
                )
            )
        except Exception as primary:
            # Constructor failures occur before an ACP reader exists.
            observation = failure_observation(
                primary, stage="startup", code="runner_transport_failed"
            )
            try:
                self._close_resources()
            except RunnerError as cleanup:
                raise RunnerError(
                    cleanup.code, observation=observation or cleanup.observation
                ) from None
            if isinstance(primary, RunnerError):
                raise primary
            from py_docker.errors import CleanupUnconfirmedError

            raise RunnerError(
                (
                    "container_termination_unverified"
                    if isinstance(primary, CleanupUnconfirmedError)
                    else "runner_transport_failed"
                ),
                observation=observation,
            ) from None

    async def initialize(self):
        """Refuse stock or incompatible adapters before any session is created."""
        from laomedo.agents.agents.base.acp.session import AcpSession

        self.acp = AcpSession(
            self.session, on_extension=self._native_event, on_precheck=self._precheck
        )
        reply = await self.acp.initialize()
        advertised = (reply.field_meta or {}).get("laomedo")
        base = {"version": 1, "rawEvents": True, "hostPolicy": True}
        if (
            advertised
            not in (
                base,
                {**base, "nativeCommands": 1},
                {**base, "nativeCommands": 1, "credentialRefresh": 1},
            )
            or type(advertised["version"]) is not int
            or type(advertised["rawEvents"]) is not bool
            or type(advertised["hostPolicy"]) is not bool
            or (
                "nativeCommands" in advertised
                and type(advertised["nativeCommands"]) is not int
            )
            or (
                "credentialRefresh" in advertised
                and type(advertised["credentialRefresh"]) is not int
            )
        ):
            raise RunnerError("initialize_rejected")
        self.native_commands_supported = advertised.get("nativeCommands") == 1
        self.credential_refresh_supported = advertised.get("credentialRefresh") == 1
        if self.managed_credential and not self.credential_refresh_supported:
            raise RunnerError("codex_credential_update_unconfirmed")
        if self.executor is not None:
            self.assert_controller_isolated()
            executor = self.executor
            await self.extension(
                "laomedo/registerExecutor",
                {
                    "environmentId": executor.environment_id,
                    "execServerUrl": "ws://127.0.0.1:39871",
                    "authBearerToken": executor.token,
                    "connectTimeoutMs": 15000,
                },
            )
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                result = await self.extension(
                    "laomedo/executorStatus",
                    {"environmentId": executor.environment_id},
                    seconds=5,
                )
                if result.get("status") == "ready":
                    self._protocol_ready = True
                    return
                if result.get("status") != "pending":
                    break
                await asyncio.sleep(0.2)
            raise RunnerError("executor_not_ready")
        self._protocol_ready = True

    async def extension(self, method, params, *, seconds=30):
        """Invoke a named adapter contract; never forward arbitrary native RPC."""
        if method not in {
            "laomedo/codexModels",
            "laomedo/preflight",
            "laomedo/registerExecutor",
            "laomedo/executorStatus",
            "laomedo/refreshCredential",
        }:
            raise RunnerError("runner_transport_failed")
        label = {
            "laomedo/codexModels": "model/list",
            "laomedo/preflight": "command/exec",
            "laomedo/registerExecutor": "environment/add",
            "laomedo/executorStatus": "environment/status",
            "laomedo/refreshCredential": "provider/credential/update",
        }[method]
        return await self.acp.extension(
            method, params, operation=label, seconds=seconds
        )

    async def refresh_credential(self, token):
        """Update only the existing controller's bearer after host account admission."""
        if not self.credential_refresh_supported or self.executor is None:
            raise RunnerError("codex_credential_update_unconfirmed")
        self.secret_redactions += (token,)
        try:
            result = await self.extension(
                "laomedo/refreshCredential", {"accessToken": token}
            )
        except RunnerError:
            raise RunnerError("codex_credential_update_unconfirmed") from None
        if result != {"updated": True}:
            raise RunnerError("codex_credential_update_unconfirmed")

    async def open(self, record, *, resume, reuse=False):
        """Bind the actual native session and confirm advertised model settings."""
        self.output_requirements = (
            verify_requirements(record["output_requirements"])
            if record.get("output_requirements")
            else None
        )
        policy = {
            "policy": "split" if self.executor else "normal",
            "model": record["requested_model"],
            "effort": record["requested_effort"],
            "dynamicTools": (
                [dynamic_tool(self.output_requirements)]
                if self.output_requirements
                else []
            ),
        }
        if self.executor:
            policy["environmentId"] = self.executor.environment_id
        if getattr(self, "mcp_access", None):
            policy["externalTools"] = list(self.mcp_access.tool_names())
            self.secret_redactions += (
                self.mcp_access.connection.token.get_secret_value(),
            )
        if reuse:
            if not resume or self.active_thread_id != record["thread_id"]:
                raise RunnerError("thread_identity_mismatch")
        else:
            await self.acp.open(
                session_id=record["thread_id"] if resume else None,
                mcp_servers=(
                    [self.mcp_access.acp_server()]
                    if getattr(self, "mcp_access", None)
                    else []
                ),
                metadata={"laomedo": policy},
            )
            self.active_thread_id = self.acp.session_id
        if resume and self.active_thread_id != record["thread_id"]:
            raise RunnerError("thread_identity_mismatch")
        for key, expected in (
            ("model", record["requested_model"]),
            ("reasoning_effort", record["requested_effort"]),
        ):
            reply = await self.acp.configure(key, expected)
            observed = next(
                (
                    option.current_value
                    for option in reply.config_options
                    if option.id == key
                ),
                None,
            )
            if observed != expected:
                raise RunnerError("unsupported_model_effort")
        # ACP notifications are handled independently of request responses.
        # Allow the fresh list to arrive before the caller publishes discovery.
        deadline = time.monotonic() + 2
        while (
            self.native_commands_supported
            and self.command_catalog() is None
            and time.monotonic() < deadline
        ):
            await asyncio.sleep(0.01)
        return self.active_thread_id

    def command_catalog(self):
        """Read detached native metadata without initiating another request or turn."""
        return self.acp.command_catalog() if self.native_commands_supported else None

    async def prompt(self, text, *, skills, cancelled, seconds, command=None):
        """Use the common health/cancel loop and require raw native completion."""
        command_kind = None
        if command is not None:
            if not self.native_commands_supported:
                raise RunnerError("native_command_not_supported")
            command_kind = CodexCommands.admit(command, self.command_catalog())
            if text != command.text() or self.output_requirements:
                raise RunnerError("native_command_context_invalid")
        self._cancelled = cancelled
        offset = len(self.events)
        failure = None
        response = None
        try:
            response = await self.acp.prompt(
                text,
                cancelled=cancelled,
                seconds=seconds,
                metadata={
                    "laomedo": {
                        **(
                            {
                                "nativeCommand": {
                                    "name": command.name,
                                    "arguments": command.arguments,
                                }
                            }
                            if command is not None
                            else {}
                        ),
                        "skills": [
                            {
                                "type": "skill",
                                "name": item["skill_id"],
                                "path": "/draft/.agents/skills/"
                                + item["skill_id"]
                                + "/SKILL.md",
                            }
                            for item in skills
                        ],
                    }
                },
                check_health=self.check_health,
            )
        except RunnerError as exc:
            failure = exc.code
        finally:
            self._cancelled = None
        if command is not None and command.name == "compact":
            evidence = self._compaction_terminal(
                [
                    e
                    for e in self.events[offset:]
                    if e.get("params", {}).get("threadId") == self.active_thread_id
                ]
            )
            if evidence is not None:
                # Upstream finishes manual compaction on the matched item. Drain
                # briefly for a late native turn failure before normal cleanup.
                deadline = time.monotonic() + 2
                while (
                    not evidence["turn_terminal_observed"]
                    and time.monotonic() < deadline
                ):
                    if cancelled.is_set() or failure:
                        break
                    try:
                        self.check_health()
                    except RunnerError as exc:
                        failure = exc.code
                        break
                    await asyncio.sleep(0.05)
                    evidence = self._compaction_terminal(
                        [
                            e
                            for e in self.events[offset:]
                            if e.get("params", {}).get("threadId")
                            == self.active_thread_id
                        ]
                    )
                    if evidence is None:
                        break
                completed = (
                    evidence is not None
                    and not failure
                    and not cancelled.is_set()
                    and response is not None
                    and response.stop_reason == "end_turn"
                )
                return CodexCommandResult(
                    command="compact",
                    status="completed" if completed else "unknown",
                    stop_reason=response.stop_reason if response is not None else None,
                    answer=response.answer or None if completed else None,
                    native_terminal=evidence,
                    error=(
                        None
                        if completed
                        else failure or "native_command_outcome_unknown"
                    ),
                )
        terminal = [
            event["params"]["turn"]
            for event in self.events[offset:]
            if event.get("method") == "turn/completed"
            and event.get("params", {}).get("threadId") == self.active_thread_id
        ]
        if command_kind == "control":
            started = any(
                event.get("method") == "turn/started"
                and event.get("params", {}).get("threadId") == self.active_thread_id
                for event in self.events[offset:]
            )
            completed = (
                not failure
                and not cancelled.is_set()
                and not started
                and not terminal
                and response is not None
                and response.stop_reason == "end_turn"
                and isinstance(response.answer, str)
                and bool(response.answer.strip())
                and len(response.answer) <= 100000
            )
            return CodexCommandResult(
                command=command.name,
                stop_reason=response.stop_reason if response is not None else None,
                status="completed" if completed else "unknown",
                answer=response.answer if completed else None,
                error=(
                    None if completed else failure or "native_command_outcome_unknown"
                ),
            )
        if not terminal and (failure or cancelled.is_set()):
            started = [
                event["params"]["turn"]
                for event in self.events[offset:]
                if event.get("method") == "turn/started"
                and event.get("params", {}).get("threadId") == self.active_thread_id
            ]
            if len(started) == 1 and isinstance(started[0].get("id"), str):
                return CodexTurn(
                    turn_id=started[0]["id"],
                    status=(
                        "cancelled"
                        if cancelled.is_set()
                        else "timeout" if failure == "turn_timeout" else "unknown"
                    ),
                    error=failure or "cancel_native_unconfirmed",
                )
        if len(terminal) != 1 or not isinstance(terminal[0].get("id"), str):
            raise RunnerError(failure or "turn_dispatch_rejected")
        turn = terminal[0]
        self.native_completion_status = turn.get("status") or "unknown"
        self.interrupt_acknowledged = (
            self.acp.cancel_sent and self.native_completion_status == "interrupted"
        )
        if failure:
            return CodexTurn(
                turn_id=turn["id"],
                status="timeout" if failure == "turn_timeout" else "unknown",
                error=failure,
            )
        status = self.native_completion_status
        error = None
        if status == "completed" and (
            response is None or response.stop_reason != "end_turn"
        ):
            # Contradictory terminal evidence cannot establish successful work.
            # Preserve the native status separately and never dispatch again.
            return CodexTurn(
                turn_id=turn["id"], status="unknown", error="runner_runtime_unknown"
            )
        if cancelled.is_set() and status == "interrupted":
            status, error = "cancelled", "cancelled_by_user"
        elif cancelled.is_set() and status != "completed":
            status, error = "cancelled", "cancel_native_unconfirmed"
        return CodexTurn(turn_id=turn["id"], status=status, error=error)

    def check_health(self, *, idle=False) -> ProcessHealthObservation:
        """Guard host authorization and the separately owned executor."""
        if getattr(self, "mcp_access", None):
            self.mcp_access.check_health()
        if self.authorization_probe is not None and not self.authorization_probe(
            idle=idle
        ):
            if idle:
                failure_code = self.authorization_failure.get("code", "auth_revoked")
                raise RunnerError(failure_code)
            raise RunnerError("auth_revoked_during_turn")
        if self.executor is not None:
            return self.executor.check_health()
        return ProcessHealthObservation(
            alive=None, scope="codex_executor_not_configured"
        )

    def assert_controller_isolated(self) -> IsolationObservation:
        """Keep native tool execution out of the credential-bearing controller."""
        if self.executor is not None:
            return self.executor.assert_controller_isolated(self.session)
        return IsolationObservation(verified=None, scope="codex_split_not_configured")

    async def preflight(self, check):
        """Run fixed zero-turn permission probes; never accept an arbitrary command."""
        commands = {
            "workspace_write": ["sh", "-c", "printf CANARY > /draft/canary.txt"],
            "canonical_write": [
                "sh",
                "-c",
                "printf FORBIDDEN > /canonical/sentinel.txt",
            ],
            "store_write": ["sh", "-c", "printf FORBIDDEN > /store/sentinel.txt"],
            "auth_read": ["sh", "-c", "cat /home/runner/.codex/auth.json >/dev/null"],
            "git_binary": ["git", "--version"],
        }
        if check not in commands:
            raise RunnerError("permission_preflight_failed")
        if self.executor:
            return self.executor.execute(CommandRequest(argv=commands[check])).exit_code
        result = await self.extension("laomedo/preflight", {"check": check})
        return result.get("exitCode")

    async def close(self):
        """Remove exact owned resources before trusting stream or cleanup closure."""
        error = None
        if self._closed:
            if getattr(self, "_close_failure", None) is not None:
                raise self._close_failure
            return
        try:
            if self.acp is not None:
                await self.acp.close()
                self.streams_closed = True
        except Exception as failure:
            error = RunnerError(
                "container_termination_unverified",
                observation=failure_observation(
                    failure, stage="cleanup", code="container_termination_unverified"
                ),
            )
        try:
            self._close_resources()
        except RunnerError as failure:
            error = RunnerError(
                failure.code,
                observation=(error.observation if error else None)
                or failure.observation,
            )
        self._closed = True
        self._close_failure = error
        if error:
            raise error

    async def models(self):
        """Read the bounded native catalogue through the named ACP extension."""
        models, seen, ids, cursor = [], set(), set(), None
        for _ in range(50):
            result = await self.extension(
                "laomedo/codexModels", {"cursor": cursor} if cursor else {}
            )
            if not isinstance(result, dict) or not isinstance(result.get("data"), list):
                raise RunnerError("model_list_rejected")
            for item in result["data"]:
                if (
                    not isinstance(item, dict)
                    or not isinstance(item.get("id"), str)
                    or not item["id"]
                    or item["id"] in ids
                ):
                    raise RunnerError("model_list_invalid_entry")
                efforts = item.get("supportedReasoningEfforts", [])
                if not isinstance(efforts, list):
                    raise RunnerError("model_list_invalid_entry")
                efforts = [
                    level.get("reasoningEffort") if isinstance(level, dict) else level
                    for level in efforts
                ]
                if not all(isinstance(level, str) and level for level in efforts):
                    raise RunnerError("model_list_invalid_entry")
                ids.add(item["id"])
                model = {"id": item["id"], "efforts": efforts}
                for native_name, name in (
                    ("displayName", "display_name"),
                    ("defaultReasoningEffort", "default_reasoning_effort"),
                ):
                    value = item.get(native_name)
                    if value is not None:
                        if not isinstance(value, str) or not value.strip():
                            raise RunnerError("model_list_invalid_entry")
                        if name == "default_reasoning_effort" and value not in efforts:
                            raise RunnerError("model_list_invalid_entry")
                        model[name] = value
                if "isDefault" in item:
                    if type(item["isDefault"]) is not bool:
                        raise RunnerError("model_list_invalid_entry")
                    model["is_default"] = item["isDefault"]
                models.append(model)
            cursor = result.get("nextCursor")
            if not cursor:
                return models
            if not isinstance(cursor, str) or cursor in seen:
                raise RunnerError("model_list_invalid_cursor")
            seen.add(cursor)
        raise RunnerError("model_list_page_limit")

    def _native_event(self, method, event):
        """Retain redacted original native events before ACP prompt returns."""
        if method != "laomedo/codexEvent":
            return
        from laomedo.agents.activity.redaction.utils import sanitized
        from laomedo.agents.activity.runner.feed import notification
        from laomedo.agents.activity.runner.feed import receipt

        line = self._redact(json.dumps(event, ensure_ascii=False))
        event = sanitized(json.loads(line))
        if not isinstance(event, dict) or not isinstance(event.get("params"), dict):
            raise RunnerError("runner_transport_failed")
        self.events.append(event)
        self.raw_log.write(json.dumps(event, ensure_ascii=False) + "\n")
        self.raw_log.flush()
        if notification(event):
            self.activity_log.write(
                json.dumps(receipt(event), ensure_ascii=False) + "\n"
            )
            self.activity_log.flush()

    def _redact(self, line):
        """Remove exact launch capabilities before any native evidence write."""
        for secret in self.secret_redactions:
            line = line.replace(secret, "[REDACTED_RUN_CAPABILITY]")
        return line

    def _precheck(self, params):
        """Validate pure output forms and retain exact binding/call evidence."""
        if self.output_requirements is None:
            raise RunnerError("runner_transport_failed")
        response = precheck_response(
            self.output_requirements, params, self.active_thread_id
        )
        if (
            params.get("tool") == "laomedo_output_precheck"
            and params.get("namespace") is None
            and params.get("threadId") == self.active_thread_id
        ):
            self.precheck_call_count += 1
            result = json.loads(response["contentItems"][0]["text"])
            if not any(
                error["code"] == "precheck_binding_mismatch"
                for error in result["errors"]
            ) and isinstance(params.get("callId"), str):
                self.verified_precheck_calls.add(params["callId"])
        return response

    def _close_resources(self):
        """Attempt both owned containers even if either removal is uncertain."""
        error = None
        try:
            if self.session is not None:
                self._session_scope.close()
                self.cleanup_confirmed = True
        except Exception as failure:
            error = RunnerError(
                "container_termination_unverified",
                observation=failure_observation(
                    failure, stage="cleanup", code="container_termination_unverified"
                ),
            )
        try:
            if self.executor is not None:
                self.executor.shutdown()
        except RunnerError as failure:
            error = RunnerError(
                failure.code,
                observation=(error.observation if error else None)
                or failure.observation,
            )
        for resource in (*self.logs, self.telemetry, self.client):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    error = error or RunnerError("runner_transport_failed")
        if error:
            raise error

    @staticmethod
    def _compaction_terminal(events):
        """Admit only one ordered native compaction pair on its observed turn."""
        starts = [e for e in events if e.get("method") == "turn/started"]
        if len(starts) != 1:
            return None
        params = starts[0].get("params", {})
        thread, turn = params.get("threadId"), params.get("turn", {}).get("id")
        if not isinstance(turn, str) or not turn:
            return None
        scoped = [e for e in events if e.get("params", {}).get("threadId") == thread]
        items = [
            e
            for e in scoped
            if e.get("params", {}).get("turnId") == turn
            and e.get("params", {}).get("item", {}).get("type") == "contextCompaction"
        ]
        incoming = [e for e in items if e.get("method") == "item/started"]
        outgoing = [e for e in items if e.get("method") == "item/completed"]
        if len(incoming) != 1 or len(outgoing) != 1:
            return None
        item = outgoing[0]["params"]["item"]
        identity = incoming[0]["params"]["item"].get("id")
        terminal = [
            e["params"]["turn"] for e in scoped if e.get("method") == "turn/completed"
        ]
        if (
            not isinstance(identity, str)
            or not identity
            or item.get("id") != identity
            or events.index(starts[0]) >= events.index(incoming[0])
            or events.index(incoming[0]) >= events.index(outgoing[0])
            or item.get("status") not in {None, "completed"}
            or item.get("error") is not None
            or any(e.get("method") == "error" for e in scoped)
            or len(terminal) > 1
            or any(
                t.get("id") != turn or t.get("status") != "completed" for t in terminal
            )
        ):
            return None
        return {
            "kind": "contextCompaction",
            "turn_id": turn,
            "item_id": identity,
            "turn_terminal_observed": bool(terminal),
        }
