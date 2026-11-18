"""Internal controls for the native-evidence boundary; no live acceptance."""

from laomedo.agents.agents.base.models import CommandRequest
import asyncio
from importlib.util import find_spec
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from laomedo.agents.interface.output.utils import requirements
from laomedo.agents.agents.codex.controller.models import CodexLaunch
from laomedo.agents.agents.codex.runtime import CodexAgentRuntime
from laomedo.agents.errors import RunnerError
from laomedo.agents.agents.base.models import NativeCommandInvocation
from laomedo.agents.agents.base.acp.models import NativeCommandCatalog


@unittest.skipUnless(
    find_spec("py_docker") and find_spec("acp"), "Requires optional runner dependencies"
)
class ControllerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.launch = CodexLaunch(
            workspace=self.root,
            canonical=self.root,
            store_mount=self.root,
            image="sha256:" + "a" * 64,
        )
        self.docker = Mock()
        native = MagicMock()
        native.__enter__.return_value = native
        native.close.return_value = None
        native.__exit__.side_effect = lambda *args: native.close()
        self.docker.sessions.open.return_value = native
        with patch("py_docker.Client", return_value=self.docker):
            self.controller = CodexAgentRuntime(
                self.launch,
                self.root,
                secret_redactions=("private-token", "telemetry-secret"),
            )
        self.controller.acp = SimpleNamespace(
            close=AsyncMock(),
            session_id="native-thread",
            cancel_sent=False,
            configure=AsyncMock(),
            prompt=AsyncMock(),
            open=AsyncMock(),
            initialize=AsyncMock(),
        )
        self.controller.active_thread_id = "native-thread"

    async def asyncTearDown(self):
        if not self.controller._closed:
            await self.controller.close()

    async def test_compact_uses_matched_native_item_without_inventing_an_answer(self):
        catalog = NativeCommandCatalog(
            commands=[{"name": "compact", "description": "Compact"}]
        )
        self.controller.acp.command_catalog = Mock(return_value=catalog)
        events = [
            {
                "method": "turn/started",
                "params": {"threadId": "native-thread", "turn": {"id": "compact-turn"}},
            },
            {
                "method": "item/started",
                "params": {
                    "threadId": "native-thread",
                    "turnId": "compact-turn",
                    "item": {"type": "contextCompaction", "id": "compact-item"},
                },
            },
            {
                "method": "item/completed",
                "params": {
                    "threadId": "native-thread",
                    "turnId": "compact-turn",
                    "item": {"type": "contextCompaction", "id": "compact-item"},
                },
            },
        ]

        async def compact(*args, **kwargs):
            self.controller.events.extend(events)
            return SimpleNamespace(stop_reason="end_turn", answer="")

        self.controller.acp.prompt.side_effect = compact
        self.controller.check_health = Mock()
        result = await self.controller.prompt(
            "/compact",
            skills=[],
            cancelled=threading.Event(),
            seconds=5,
            command=NativeCommandInvocation(
                name="compact", catalog_revision=catalog.revision()
            ),
        )
        self.assertEqual(result.status, "completed")
        self.assertIsNone(result.answer)
        self.assertIsNone(result.turn_id)
        self.assertEqual(
            result.native_terminal,
            {
                "kind": "contextCompaction",
                "turn_id": "compact-turn",
                "item_id": "compact-item",
                "turn_terminal_observed": False,
            },
        )
        cancelled = threading.Event()
        cancelled.set()
        stopped = await self.controller.prompt(
            "/compact",
            skills=[],
            cancelled=cancelled,
            seconds=5,
            command=NativeCommandInvocation(
                name="compact", catalog_revision=catalog.revision()
            ),
        )
        self.assertEqual(stopped.status, "unknown")
        self.assertIsNone(stopped.answer)
        for wrong in [
            events[:-1],
            [events[0], events[2], events[1]],
            [
                *events,
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": "native-thread",
                        "turn": {"id": "compact-turn", "status": "failed"},
                    },
                },
            ],
            [*events, {"method": "error", "params": {"threadId": "native-thread"}}],
        ]:
            self.assertIsNone(self.controller._compaction_terminal(wrong))

    async def test_open_observes_delayed_catalog_before_discovery(self):
        """A notification queued after the response is retained before publication."""
        catalog = NativeCommandCatalog(
            commands=[{"name": "status", "description": "Status"}]
        )
        observed = None
        self.controller.acp.command_catalog = lambda: observed
        self.controller.acp.configure.side_effect = lambda key, value: SimpleNamespace(
            config_options=[SimpleNamespace(id=key, current_value=value)]
        )

        async def advertise():
            nonlocal observed
            await asyncio.sleep(0.02)
            observed = catalog

        pending = asyncio.create_task(advertise())
        await self.controller.open(
            {"requested_model": "model", "requested_effort": "low"}, resume=False
        )
        await pending
        self.assertEqual(self.controller.command_catalog(), catalog)

    async def test_explicit_control_command_has_no_fabricated_native_turn(self):
        """Native control text settles separately from strict ordinary prompts."""
        catalog = NativeCommandCatalog(
            commands=[{"name": "status", "description": "Status"}]
        )
        self.controller.acp.command_catalog = Mock(return_value=catalog)
        self.controller.acp.prompt.return_value = SimpleNamespace(
            stop_reason="end_turn", answer="Actual native status"
        )
        request = NativeCommandInvocation(
            name="status", catalog_revision=catalog.revision()
        )
        result = await self.controller.prompt(
            "/status",
            skills=[],
            cancelled=threading.Event(),
            seconds=1,
            command=request,
        )
        self.assertIsNone(result.turn_id)
        self.assertEqual(result.answer, "Actual native status")
        self.assertEqual(result.status, "completed")
        self.assertNotIn("usage", result.model_dump())
        with self.assertRaisesRegex(RunnerError, "turn_dispatch_rejected"):
            await self.controller.prompt(
                "/status", skills=[], cancelled=threading.Event(), seconds=1
            )

    async def test_control_command_missing_answer_is_unknown_and_stale_catalog_refuses(
        self,
    ):
        """A terminal response alone is not positive native command completion."""
        catalog = NativeCommandCatalog(
            commands=[{"name": "status", "description": "Status"}]
        )
        self.controller.acp.command_catalog = Mock(return_value=catalog)
        self.controller.acp.prompt.return_value = SimpleNamespace(
            stop_reason="end_turn", answer=""
        )
        request = NativeCommandInvocation(
            name="status", catalog_revision=catalog.revision()
        )
        result = await self.controller.prompt(
            "/status",
            skills=[],
            cancelled=threading.Event(),
            seconds=1,
            command=request,
        )
        self.assertEqual(result.status, "unknown")
        self.controller.acp.prompt.reset_mock()
        with self.assertRaisesRegex(RunnerError, "native_command_catalog_changed"):
            await self.controller.prompt(
                "/status",
                skills=[],
                cancelled=threading.Event(),
                seconds=1,
                command=request.model_copy(update={"catalog_revision": "0" * 64}),
            )
        self.controller.acp.prompt.assert_not_awaited()

    async def test_stock_and_wrong_version_are_refused_before_session_creation(self):
        for value in (
            None,
            {},
            {"laomedo": {"version": 2, "rawEvents": True, "hostPolicy": True}},
            {"laomedo": {"version": True, "rawEvents": True, "hostPolicy": True}},
            {"laomedo": {"version": 1, "rawEvents": 1, "hostPolicy": True}},
        ):
            acp = Mock(
                initialize=AsyncMock(return_value=SimpleNamespace(field_meta=value))
            )
            acp.close = AsyncMock()
            with patch(
                "laomedo.agents.agents.base.acp.session.AcpSession",
                return_value=acp,
            ):
                with self.assertRaisesRegex(RunnerError, "initialize_rejected"):
                    await self.controller.initialize()
            acp.open.assert_not_called()

    async def test_native_completion_before_acp_response_is_observed(self):
        async def finish(*args, **kwargs):
            self.controller._native_event(
                "laomedo/codexEvent",
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": "native-thread",
                        "turn": {"id": "turn", "status": "completed"},
                    },
                },
            )

            return SimpleNamespace(stop_reason="end_turn")

        self.controller.acp.prompt.side_effect = finish
        turn = await self.controller.prompt(
            "task", skills=[], cancelled=threading.Event(), seconds=1
        )
        self.assertEqual((turn.turn_id, turn.status), ("turn", "completed"))
        self.assertFalse(self.controller.interrupt_acknowledged)

    async def test_conflicting_acp_stop_cannot_confirm_native_success(self):
        for reason in ("max_tokens", "refusal", "cancelled", "max_turn_requests"):
            with self.subTest(stop_reason=reason):

                async def finish(*args, **kwargs):
                    self.controller.events.append(
                        {
                            "method": "turn/completed",
                            "params": {
                                "threadId": "native-thread",
                                "turn": {"id": "turn", "status": "completed"},
                            },
                        }
                    )
                    return SimpleNamespace(stop_reason=reason)

                self.controller.acp.prompt.reset_mock()
                self.controller.acp.prompt.side_effect = finish
                turn = await self.controller.prompt(
                    "task", skills=[], cancelled=threading.Event(), seconds=1
                )
                self.assertEqual(
                    (turn.turn_id, turn.status, turn.error),
                    ("turn", "unknown", "runner_runtime_unknown"),
                )
                self.assertEqual(self.controller.native_completion_status, "completed")
                self.controller.acp.prompt.assert_awaited_once()

    async def test_child_completion_cannot_close_root_turn(self):
        async def finish(*args, **kwargs):
            self.controller.events.append(
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": "child",
                        "turn": {"id": "turn", "status": "completed"},
                    },
                }
            )

        self.controller.acp.prompt.side_effect = finish
        with self.assertRaisesRegex(RunnerError, "turn_dispatch_rejected"):
            await self.controller.prompt(
                "task", skills=[], cancelled=threading.Event(), seconds=1
            )

    async def test_cancel_requires_matching_native_interrupted_completion(self):
        cancelled = threading.Event()
        cancelled.set()
        self.controller.acp.cancel_sent = True

        async def finish(*args, **kwargs):
            self.controller.events.append(
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": "native-thread",
                        "turn": {"id": "turn", "status": "interrupted"},
                    },
                }
            )

        self.controller.acp.prompt.side_effect = finish
        turn = await self.controller.prompt(
            "task", skills=[], cancelled=cancelled, seconds=1
        )
        self.assertEqual((turn.status, turn.error), ("cancelled", "cancelled_by_user"))
        self.assertTrue(self.controller.interrupt_acknowledged)
        self.assertEqual(self.controller.native_completion_status, "interrupted")

    async def test_unconfirmed_terminal_response_preserves_started_turn_and_failure(
        self,
    ):
        for user_cancel, code, status in (
            (True, "cancel_native_unconfirmed", "cancelled"),
            (False, "turn_timeout", "timeout"),
        ):
            with self.subTest(user_cancel=user_cancel):
                cancelled = threading.Event()
                if user_cancel:
                    cancelled.set()
                self.controller.acp.cancel_sent = True
                self.controller.acp.prompt.reset_mock()

                async def fail(*args, **kwargs):
                    self.controller.events.append(
                        {
                            "method": "turn/started",
                            "params": {
                                "threadId": "native-thread",
                                "turn": {"id": "started-turn"},
                            },
                        }
                    )
                    raise RunnerError(code)

                self.controller.acp.prompt.side_effect = fail
                turn = await self.controller.prompt(
                    "task", skills=[], cancelled=cancelled, seconds=1
                )
                self.assertEqual(
                    (turn.turn_id, turn.status, turn.error),
                    ("started-turn", status, code),
                )
                self.assertFalse(self.controller.interrupt_acknowledged)
                self.assertIsNone(self.controller.native_completion_status)
                self.controller.acp.prompt.assert_awaited_once()

    async def test_cancel_without_interrupted_completion_stays_unconfirmed(self):
        cancelled = threading.Event()
        cancelled.set()
        self.controller.acp.cancel_sent = True
        for native_status in ("failed", "unknown"):
            with self.subTest(native_status=native_status):

                async def finish(*args, **kwargs):
                    self.controller.events.append(
                        {
                            "method": "turn/completed",
                            "params": {
                                "threadId": "native-thread",
                                "turn": {"id": "turn", "status": native_status},
                            },
                        }
                    )
                    return SimpleNamespace(stop_reason="cancelled")

                self.controller.acp.prompt.side_effect = finish
                turn = await self.controller.prompt(
                    "task", skills=[], cancelled=cancelled, seconds=1
                )
                self.assertEqual(
                    (turn.turn_id, turn.status, turn.error),
                    ("turn", "cancelled", "cancel_native_unconfirmed"),
                )
                self.assertEqual(
                    self.controller.native_completion_status, native_status
                )
                self.assertFalse(self.controller.interrupt_acknowledged)

    async def test_revocation_and_executor_health_use_shared_prompt_guard(self):
        self.controller.authorization_probe = lambda: False
        with self.assertRaisesRegex(RunnerError, "auth_revoked_during_turn"):
            self.controller.check_health()
        self.controller.authorization_probe = None
        self.controller.executor = Mock()
        self.controller.executor.check_health.side_effect = RunnerError("executor_lost")
        with self.assertRaisesRegex(RunnerError, "executor_lost"):
            self.controller.check_health()
        # Shared ACP cancellation/health tests exercise actual guard scheduling.

    async def test_native_and_telemetry_secrets_are_removed_before_both_logs(self):
        self.controller._native_event(
            "laomedo/codexEvent",
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "text": "private-token telemetry-secret Bearer abc.def",
                        "access_token": "hidden",
                    }
                },
            },
        )
        for name in ("raw-events.jsonl", "activity-events.jsonl"):
            text = (self.root / name).read_text()
            for private in ("private-token", "telemetry-secret", "abc.def", "hidden"):
                self.assertNotIn(private, text)
            self.assertIn("[REDACTED_RUN_CAPABILITY]", text)

    async def test_precheck_rejections_keep_verified_call_ids_but_not_wrong_bindings(
        self,
    ):
        pin = requirements(
            {
                "schema_version": 1,
                "fields": [{"name": "report", "type": "string", "required": True}],
            }
        )
        self.controller.output_requirements = pin
        request = {
            "threadId": "native-thread",
            "callId": "call",
            "namespace": None,
            "tool": "laomedo_output_precheck",
            "arguments": {
                "requirements_revision": pin["requirements_revision"],
                "submission": {},
            },
        }
        rejected = self.controller._precheck(request)
        self.assertEqual(self.controller.verified_precheck_calls, {"call"})
        self.assertEqual(
            json.loads(rejected["contentItems"][0]["text"])["contract_status"],
            "rejected",
        )
        self.controller._precheck({**request, "callId": "wrong", "threadId": "other"})
        self.assertEqual(self.controller.precheck_call_count, 1)
        self.assertEqual(self.controller.verified_precheck_calls, {"call"})

    async def test_split_preflight_uses_only_fixed_probe_argv(self):
        self.controller.executor = Mock()
        self.controller.executor.execute.return_value = SimpleNamespace(exit_code=17)
        for check, argv in (
            ("workspace_write", ["sh", "-c", "printf CANARY > /draft/canary.txt"]),
            (
                "canonical_write",
                ["sh", "-c", "printf FORBIDDEN > /canonical/sentinel.txt"],
            ),
            ("store_write", ["sh", "-c", "printf FORBIDDEN > /store/sentinel.txt"]),
            ("auth_read", ["sh", "-c", "cat /home/runner/.codex/auth.json >/dev/null"]),
            ("git_binary", ["git", "--version"]),
        ):
            with self.subTest(check=check):
                self.assertEqual(await self.controller.preflight(check), 17)
                self.controller.executor.execute.assert_called_once_with(
                    CommandRequest(argv=argv)
                )
                self.controller.executor.execute.reset_mock()
        with self.assertRaisesRegex(RunnerError, "^permission_preflight_failed$"):
            await self.controller.preflight("sh -c arbitrary-command")
        self.controller.executor.execute.assert_not_called()

    async def test_unsplit_preflight_uses_the_named_adapter_extension(self):
        self.controller.extension = AsyncMock(return_value={"exitCode": 23})
        self.assertEqual(await self.controller.preflight("workspace_write"), 23)
        self.controller.extension.assert_awaited_once_with(
            "laomedo/preflight", {"check": "workspace_write"}
        )
        self.controller.extension.reset_mock()
        with self.assertRaisesRegex(RunnerError, "^permission_preflight_failed$"):
            await self.controller.preflight("arbitrary-command")
        self.controller.extension.assert_not_called()

    async def test_extension_boundary_keeps_native_allowlist_and_safe_operation(self):
        self.controller.acp.extension = AsyncMock(return_value={"models": []})
        self.assertEqual(
            await self.controller.extension("laomedo/codexModels", {}, seconds=2),
            {"models": []},
        )
        self.controller.acp.extension.assert_awaited_once_with(
            "laomedo/codexModels", {}, operation="model/list", seconds=2
        )
        self.controller.acp.extension.reset_mock()
        with self.assertRaisesRegex(RunnerError, "^runner_transport_failed$"):
            await self.controller.extension("terminal/create", {"command": "anything"})
        self.controller.acp.extension.assert_not_called()

    async def test_unconfirmed_cleanup_cannot_pass(self):
        self.controller.acp.close.side_effect = RuntimeError(
            "private cleanup diagnostic"
        )
        with self.assertRaisesRegex(RunnerError, "container_termination_unverified"):
            await self.controller.close()
        self.assertFalse(self.controller.streams_closed)

    async def test_repeated_close_preserves_session_cleanup_failure(self):
        self.controller.session.close.side_effect = RuntimeError("cleanup uncertain")
        with self.assertRaises(RunnerError) as first:
            await self.controller.close()
        with self.assertRaises(RunnerError) as second:
            await self.controller.close()
        self.assertIs(second.exception, first.exception)
        self.assertFalse(self.controller.cleanup_confirmed)
        self.controller.session.close.assert_called_once()
