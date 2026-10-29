"""Codex launch policy and native evidence over the shared ACP client."""

import asyncio
import json
import time

from laomedo.agents.contracts import output
from laomedo.agents.protocol.acp.session import AcpSession
from laomedo.agents.providers.codex import settings
from laomedo.agents.providers.codex.controller.models import CodexLaunch, CodexTurn
from laomedo.agents.providers.codex.controller.settings import Settings
from laomedo.agents.runtime.errors import RunnerError


class CodexController:
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
        from py_docker import Client
        from py_docker.connection.settings import ConnectionSettings
        from py_docker.sessions.models import ContainerSession
        from py_docker.streams.models import StreamLimits

        self.client = Client(
            settings=ConnectionSettings(timeout_seconds=15), environment=env
        )
        self.container_name = launch.name
        self.session = self.acp = self.executor = self.telemetry = None
        self.events = []
        self.output_requirements = None
        self.active_thread_id = None
        self.precheck_call_count = 0
        self.verified_precheck_calls = set()
        self.native_completion_status = None
        self.interrupt_acknowledged = False
        self.authorization_probe = None
        self.cleanup_confirmed = self.streams_closed = False
        self._closed = False
        self.secret_redactions = tuple(value for value in secret_redactions if value)
        self.logs = []
        try:
            if split is not None:
                from laomedo.agents.providers.codex.split.executor import Executor
                from laomedo.agents.providers.codex.split.models import SplitLaunch

                self.executor = Executor(
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
            arguments = (
                json.loads(environment["LAOMEDO_CODEX_ARGS"].get_secret_value())
                if "LAOMEDO_CODEX_ARGS" in environment
                else []
            )
            if settings.Settings().multi_agent == "1":
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
            from laomedo.activity.runner.settings import Settings as ActivitySettings

            if ActivitySettings().otel == "1":
                from laomedo.activity.runner.telemetry import LaunchTelemetry

                self.telemetry = LaunchTelemetry(evidence)
                arguments += self.telemetry.arguments()
                self.secret_redactions += (self.telemetry.token,)
            from pydantic import SecretStr

            environment["LAOMEDO_CODEX_ARGS"] = SecretStr(json.dumps(arguments))
            spec = spec.model_copy(update={"environment": environment})
            self.raw_log = (evidence / "raw-events.jsonl").open("a", encoding="utf-8")
            self.logs.append(self.raw_log)
            self.activity_log = (evidence / "activity-events.jsonl").open(
                "a", encoding="utf-8"
            )
            self.logs.append(self.activity_log)
            self.session = self.client.sessions.open(
                ContainerSession(
                    spec=spec,
                    limits=StreamLimits(
                        seconds=lifetime_seconds, max_bytes=Settings.load().max_bytes
                    ),
                    receipt_path=receipt_path
                    or evidence / settings.NATIVE_RECEIPT_FILENAME,
                )
            )
        except Exception as primary:
            # Constructor failures occur before an ACP reader exists.
            try:
                self._close_resources()
            except RunnerError:
                raise
            if isinstance(primary, RunnerError):
                raise primary
            from py_docker.errors import CleanupUnconfirmedError

            raise RunnerError(
                "container_termination_unverified"
                if isinstance(primary, CleanupUnconfirmedError)
                else "runner_transport_failed"
            ) from None

    async def initialize(self):
        """Refuse stock or incompatible adapters before any session is created."""
        self.acp = AcpSession(
            self.session, on_extension=self._native_event, on_precheck=self._precheck
        )
        reply = await self.acp.initialize()
        advertised = (reply.field_meta or {}).get("laomedo")
        if advertised != {"version": 1, "rawEvents": True, "hostPolicy": True}:
            raise RunnerError("initialize_rejected")
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
                    return
                if result.get("status") != "pending":
                    break
                await asyncio.sleep(0.2)
            raise RunnerError("executor_not_ready")

    async def extension(self, method, params, *, seconds=30):
        """Invoke a named adapter contract; never forward arbitrary native RPC."""
        if method not in {
            "laomedo/codexModels",
            "laomedo/preflight",
            "laomedo/registerExecutor",
            "laomedo/executorStatus",
        }:
            raise RunnerError("runner_transport_failed")
        return await self.acp._request(
            self.acp.connection.ext_method(method, params), "initialize", seconds
        )

    async def open(self, record, *, resume):
        """Bind the actual native session and confirm advertised model settings."""
        self.output_requirements = (
            output.verify_requirements(record["output_requirements"])
            if record.get("output_requirements")
            else None
        )
        policy = {
            "policy": "split" if self.executor else "normal",
            "model": record["requested_model"],
            "effort": record["requested_effort"],
            "dynamicTools": [output.dynamic_tool(self.output_requirements)]
            if self.output_requirements
            else [],
        }
        if self.executor:
            policy["environmentId"] = self.executor.environment_id
        await self.acp.open(
            session_id=record["thread_id"] if resume else None,
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
        return self.active_thread_id

    async def prompt(self, text, *, skills, cancelled, seconds):
        """Use the common health/cancel loop and require raw native completion."""
        offset = len(self.events)
        failure = None
        try:
            await self.acp.prompt(
                text,
                cancelled=cancelled,
                seconds=seconds,
                metadata={
                    "laomedo": {
                        "skills": [
                            {
                                "type": "skill",
                                "name": item["skill_id"],
                                "path": "/draft/.agents/skills/"
                                + item["skill_id"]
                                + "/SKILL.md",
                            }
                            for item in skills
                        ]
                    }
                },
                check_health=self.check_health,
            )
        except RunnerError as exc:
            failure = exc.code
        terminal = [
            event["params"]["turn"]
            for event in self.events[offset:]
            if event.get("method") == "turn/completed"
            and event.get("params", {}).get("threadId") == self.active_thread_id
        ]
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
                    status="cancelled"
                    if cancelled.is_set()
                    else "timeout"
                    if failure == "turn_timeout"
                    else "unknown",
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
        if cancelled.is_set() and status == "interrupted":
            status, error = "cancelled", "cancelled_by_user"
        elif cancelled.is_set() and status != "completed":
            status, error = "cancelled", "cancel_native_unconfirmed"
        return CodexTurn(turn_id=turn["id"], status=status, error=error)

    def check_health(self):
        """Guard host authorization and the separately owned executor."""
        if self.authorization_probe is not None and not self.authorization_probe():
            raise RunnerError("auth_revoked_during_turn")
        if self.executor is not None:
            self.executor.check_health()

    def assert_controller_isolated(self):
        """Keep native tool execution out of the credential-bearing controller."""
        if self.executor is not None:
            self.executor.assert_controller_isolated(self.session)

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
            return self.executor.exec_probe(commands[check]).exit_code
        result = await self.extension("laomedo/preflight", {"check": check})
        return result.get("exitCode")

    def _native_event(self, method, event):
        """Retain redacted original native events before ACP prompt returns."""
        if method != "laomedo/codexEvent":
            return
        from laomedo.activity.redaction.utils import sanitized
        from laomedo.activity.runner import feed

        line = self._redact(json.dumps(event, ensure_ascii=False))
        event = sanitized(json.loads(line))
        if not isinstance(event, dict) or not isinstance(event.get("params"), dict):
            raise RunnerError("runner_transport_failed")
        self.events.append(event)
        self.raw_log.write(json.dumps(event, ensure_ascii=False) + "\n")
        self.raw_log.flush()
        if feed.notification(event):
            self.activity_log.write(
                json.dumps(feed.receipt(event), ensure_ascii=False) + "\n"
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
        response = output.precheck_response(
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

    async def close(self):
        """Remove exact owned resources before trusting stream or cleanup closure."""
        error = None
        if self._closed:
            return
        try:
            if self.acp is not None:
                await self.acp.close()
                self.streams_closed = True
        except Exception:
            error = RunnerError("container_termination_unverified")
        try:
            self._close_resources()
        except RunnerError as failure:
            error = failure
        self._closed = True
        if error:
            raise error

    def _close_resources(self):
        """Attempt both owned containers even if either removal is uncertain."""
        error = None
        try:
            if self.session is not None:
                self.session.close()
                self.cleanup_confirmed = True
        except Exception:
            error = RunnerError("container_termination_unverified")
        try:
            if self.executor is not None:
                self.executor.close()
        except RunnerError as failure:
            error = failure
        for resource in (*self.logs, self.telemetry, self.client):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    error = error or RunnerError("runner_transport_failed")
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
                models.append({"id": item["id"], "efforts": efforts})
            cursor = result.get("nextCursor")
            if not cursor:
                return models
            if not isinstance(cursor, str) or cursor in seen:
                raise RunnerError("model_list_invalid_cursor")
            seen.add(cursor)
        raise RunnerError("model_list_page_limit")
