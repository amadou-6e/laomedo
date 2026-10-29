"""Internal controls for the native-evidence boundary; no live acceptance."""

import asyncio
from importlib.util import find_spec
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from laomedo.agents.contracts.output import requirements
from laomedo.agents.providers.codex.controller.models import CodexLaunch
from laomedo.agents.providers.codex.controller.service import CodexController
from laomedo.agents.runtime.errors import RunnerError


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
        with patch("py_docker.Client", return_value=self.docker):
            self.controller = CodexController(
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
        await self.controller.close()

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
                "laomedo.agents.protocol.acp.session.AcpSession",
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

        self.controller.acp.prompt.side_effect = finish
        turn = await self.controller.prompt(
            "task", skills=[], cancelled=threading.Event(), seconds=1
        )
        self.assertEqual((turn.turn_id, turn.status), ("turn", "completed"))
        self.assertFalse(self.controller.interrupt_acknowledged)

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

    async def test_unconfirmed_cleanup_cannot_pass(self):
        self.controller.acp.close.side_effect = RuntimeError(
            "private cleanup diagnostic"
        )
        with self.assertRaisesRegex(RunnerError, "container_termination_unverified"):
            await self.controller.close()
        self.assertFalse(self.controller.streams_closed)
