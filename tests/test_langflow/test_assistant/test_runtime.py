"""Conversation reconciliation and cancellation controls with real application storage."""

from pathlib import Path
from datetime import datetime, timezone
import tempfile
import time
import unittest
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from langflow.services.database.models.user.model import User

from laomedo.agents.activity.models import (
    ActivityPage,
    ActivityProjection,
    ActivityRecord,
    MessageActivity,
)
from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.models import (
    ConversationRequest,
    MessageRequest,
    AuthoringContext,
    DraftRequest,
)
from laomedo.integrations.langflow.assistant.persistence import AssistantStore
from laomedo.integrations.langflow.assistant.runtime import AssistantRuntime
from laomedo.integrations.langflow.assistant.settings import AssistantSettings


class RunnerObservation:
    """Retain observed records and control calls, never infer or dispatch a model."""

    def __init__(self, record):
        self.record = record
        self.instance_id = record["runner_instance_id"]
        self.requests = []
        self.dispatch = None
        self.settled = True

    def request(self, method, path, body=None):
        self.requests.append((method, path))
        if "/activity?" in path:
            raise AssistantError("activity_journal_unavailable")
        if "/resume/" in path:
            return self.dispatch
        return self.record

    def is_settled(self, run_id):
        return self.settled


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_resumed_attempt_uses_durable_dispatch_owner_not_original_run_creator(
        self,
    ):
        await self.bind()
        await self.runtime.reconcile(self.owner, self.identifier)
        following, _ = await self.store.reserve(
            self.owner,
            self.identifier,
            MessageRequest(client_message_id=uuid4(), text="After restart"),
            session_key="fixture",
        )
        self.runner.instance_id = str(uuid4())
        await self.store.rebind_completed(
            self.owner, self.identifier, UUID(following["id"]), self.runner.instance_id
        )
        await self.store.observe(
            self.owner,
            self.identifier,
            UUID(following["id"]),
            run_id=self.run_id,
            native_attempt_id=following["attempt_id"],
            instance_id=self.runner.instance_id,
            state="running",
        )
        self.record["activity_attempt_id"] = following["attempt_id"]
        self.runner.dispatch = {
            "status": "finished",
            "runner_instance_id": self.runner.instance_id,
        }
        self.assertTrue(await self.runtime.reconcile(self.owner, self.identifier))
        detail = await self.store.detail(self.owner, self.identifier)
        self.assertEqual(detail["conversation"]["state"], "idle")
        self.assertEqual(detail["messages"][-1]["state"], "completed")
        self.assertNotEqual(self.record["runner_instance_id"], self.runner.instance_id)

    async def test_duplicate_submission_is_observed_without_runner_start_even_at_capacity(
        self,
    ):
        self.runtime.jobs = {uuid4(): object() for _ in range(4)}
        result = await self.runtime.send(
            self.owner,
            "fixture",
            self.identifier,
            MessageRequest(
                client_message_id=UUID(self.message["client_message_id"]), text="Build"
            ),
        )
        self.assertEqual(result["id"], self.message["id"])
        self.runtime.runner.assert_not_awaited()

    async def test_cached_page_tail_ends_explicitly_when_live_history_is_unavailable(
        self,
    ):
        await self.bind()
        page = ActivityPage(
            run_id=self.run_id,
            attempt_id=self.native_id,
            available=True,
            records=[
                ActivityRecord(
                    sequence=index,
                    occurred_at=None,
                    observed_at=datetime.now(timezone.utc),
                    event=MessageActivity(
                        message_id="answer",
                        thread_id="original-session",
                        role="assistant",
                        text="Version " + str(index),
                    ),
                )
                for index in range(1, 501)
            ],
            next_after=500,
            has_more=True,
            closed=True,
            complete=True,
            reason=None,
            projection=ActivityProjection.empty(),
            projection_revision=1,
            thread_id="original-session",
        )
        await self.store.cache_activity(
            self.owner, self.identifier, self.message_id, page.to_payload()
        )
        await self.runtime.reconcile(self.owner, self.identifier)
        first = await self.runtime.activity(
            self.owner, self.identifier, UUID(self.message["attempt_id"]), 0
        )
        self.assertTrue(first["has_more"])
        tail = await self.runtime.activity(
            self.owner, self.identifier, UUID(self.message["attempt_id"]), 500
        )
        self.assertFalse(tail["has_more"])
        self.assertFalse(tail["complete"])
        self.assertEqual(tail["reason"], "activity_journal_unavailable")
        self.assertIn("&after=500&limit=100", self.runner.requests[-1][1])

    async def test_uncertain_save_allows_only_identical_receipt_reconciliation(self):
        context = AuthoringContext(
            owner_id=self.owner,
            conversation_id=self.identifier,
            message_id=self.message_id,
            attempt_id=self.message["attempt_id"],
            session_key="fixture",
        )
        self.runtime.authorize = AsyncMock()
        request = DraftRequest(
            draft_key="original",
            name="Draft",
            spec={
                "nodes": [{"key": "agent", "component_type": "Agent"}],
                "edges": [],
                "allow_incomplete": True,
            },
        )
        workflows = AsyncMock()
        workflows.save.side_effect = AssistantError("assistant_save_outcome_unknown")
        with self.assertRaises(AssistantError):
            await self.runtime.save(context, workflows, request)
        with self.assertRaises(AssistantError) as refused:
            await self.runtime.save(
                context,
                workflows,
                request.model_copy(update={"draft_key": "replacement"}),
            )
        self.assertEqual(
            refused.exception.code, "assistant_save_reconciliation_required"
        )
        self.assertEqual(workflows.save.await_count, 1)
        workflows.save.side_effect = None
        workflows.save.return_value = {"receipt_id": "committed"}
        self.assertEqual(
            await self.runtime.save(context, workflows, request),
            {"receipt_id": "committed"},
        )
        self.assertNotIn(self.message_id, self.runtime.uncertain_saves)

    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = create_async_engine(
            "sqlite+aiosqlite:///" + (Path(self.directory.name) / "app.db").as_posix()
        )
        async with self.engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)
        self.store = AssistantStore(self.engine)
        self.owner, self.run_id, self.native_id = uuid4(), str(uuid4()), str(uuid4())
        async with self.store.transaction() as session:
            session.add(
                User(
                    id=self.owner,
                    username="fixture-owner",
                    password="fixture",
                    is_active=True,
                )
            )
        await self.store.admit_session("fixture", self.owner, time.time() + 1000)
        conversation = await self.store.create(
            self.owner,
            ConversationRequest(model="fixture", effort="low"),
            session_key="fixture",
        )
        self.identifier = UUID(conversation["id"])
        self.message, _ = await self.store.reserve(
            self.owner,
            self.identifier,
            MessageRequest(client_message_id=uuid4(), text="Build"),
            session_key="fixture",
        )
        self.message_id = UUID(self.message["id"])
        self.record = {
            "run_id": self.run_id,
            "activity_initial_attempt_id": self.native_id,
            "activity_attempt_id": self.native_id,
            "runner_instance_id": str(uuid4()),
            "status": "completed",
            "attempt_finished": True,
            "controller_cleanup": "confirmed",
            "container_ownership": {"cleanup_verified": True},
            "thread_id": "original-session",
            "post_run_hash": "sha256:" + "a" * 64,
            "answer": "Done",
        }
        self.runner = RunnerObservation(self.record)
        self.runtime = AssistantRuntime(
            AssistantSettings(app_url="http://127.0.0.1:17881")
        )
        self.runtime.store, self.runtime.ready = self.store, True
        self.runtime.runner = AsyncMock(return_value=self.runner)

    async def asyncTearDown(self):
        await self.engine.dispose()
        self.directory.cleanup()

    async def bind(self):
        await self.store.observe(
            self.owner,
            self.identifier,
            self.message_id,
            run_id=self.run_id,
            native_attempt_id=self.native_id,
            instance_id=self.runner.instance_id,
            state="running",
        )

    async def test_native_completion_cannot_unlock_send_before_tool_authority_drains(
        self,
    ):
        await self.bind()
        context = AuthoringContext(
            owner_id=self.owner,
            conversation_id=self.identifier,
            message_id=self.message_id,
            attempt_id=self.message["attempt_id"],
            session_key="fixture",
        )
        self.runtime.contexts[self.message_id] = context
        self.assertTrue(
            await self.runtime.reconcile(
                self.owner, self.identifier, defer_settlement=True
            )
        )
        self.assertFalse(await self.runtime.reconcile(self.owner, self.identifier))
        self.assertIsNotNone(
            (await self.store.detail(self.owner, self.identifier))["conversation"][
                "active_message_id"
            ]
        )
        self.runtime.contexts.clear()
        self.assertTrue(await self.runtime.reconcile(self.owner, self.identifier))
        detail = await self.store.detail(self.owner, self.identifier)
        self.assertEqual(detail["conversation"]["state"], "idle")
        self.assertEqual(detail["messages"][0]["response"], "Done")
        self.assertTrue(all(method == "GET" for method, _ in self.runner.requests))

    async def test_lost_first_ack_after_restart_keeps_history_without_binding_new_runner(
        self,
    ):
        self.runner.instance_id = str(uuid4())
        await self.store.observe(
            self.owner,
            self.identifier,
            self.message_id,
            state="unknown",
            error="assistant_dispatch_unknown",
        )
        self.assertTrue(await self.runtime.reconcile(self.owner, self.identifier))
        detail = await self.store.detail(self.owner, self.identifier)
        self.assertEqual(detail["conversation"]["state"], "attention")
        self.assertIsNone(detail["conversation"]["runner_instance_id"])
        self.assertIsNone(detail["conversation"]["workspace_hash"])
        self.assertEqual(detail["messages"][0]["text"], "Build")
        self.assertTrue(all(method == "GET" for method, _ in self.runner.requests))

    async def test_definite_resume_refusal_is_observed_without_waiting_for_an_attempt_that_never_started(
        self,
    ):
        await self.bind()
        await self.runtime.reconcile(self.owner, self.identifier)
        message, _ = await self.store.reserve(
            self.owner,
            self.identifier,
            MessageRequest(client_message_id=uuid4(), text="Next"),
            session_key="fixture",
        )
        await self.store.observe(
            self.owner,
            self.identifier,
            UUID(message["id"]),
            run_id=self.run_id,
            native_attempt_id=message["attempt_id"],
            instance_id=self.runner.instance_id,
            state="running",
        )
        self.runner.dispatch = {
            "status": "failed",
            "error_category": "resume_binding_mismatch",
            "runner_instance_id": self.runner.instance_id,
        }
        self.assertTrue(await self.runtime.reconcile(self.owner, self.identifier))
        detail = await self.store.detail(self.owner, self.identifier)
        self.assertEqual(detail["messages"][-1]["state"], "failed")
        self.assertIsNone(detail["conversation"]["active_message_id"])
        self.assertTrue(all(method == "GET" for method, _ in self.runner.requests))

    async def test_stop_before_run_identity_is_durable_and_cancels_after_lookup(self):
        await self.runtime.stop(
            self.owner, self.identifier, UUID(self.message["attempt_id"])
        )
        self.record.update(status="running", attempt_finished=False)
        self.runner.settled = False
        self.assertFalse(await self.runtime.reconcile(self.owner, self.identifier))
        _, message = await self.store.message(
            self.owner, self.identifier, self.message_id
        )
        self.assertTrue(message.stop_requested)
        self.assertEqual(
            [path for method, path in self.runner.requests if method == "POST"],
            ["/v1/runs/" + self.run_id + "/cancel"],
        )

    async def test_stop_preserves_unknown_outcome_until_actual_reconciliation(self):
        await self.store.observe(
            self.owner,
            self.identifier,
            self.message_id,
            state="unknown",
            error="assistant_dispatch_unknown",
            reconciled=True,
        )
        await self.runtime.stop(
            self.owner, self.identifier, UUID(self.message["attempt_id"])
        )
        _, message = await self.store.message(
            self.owner, self.identifier, self.message_id
        )
        self.assertEqual(message.state, "unknown")
        self.assertTrue(message.stop_requested)

    async def test_retained_activity_reopens_without_starting_docker_or_a_provider(
        self,
    ):
        await self.bind()
        page = ActivityPage(
            run_id=self.run_id,
            attempt_id=self.native_id,
            available=True,
            records=[],
            next_after=0,
            has_more=False,
            closed=True,
            complete=True,
            reason=None,
            projection=ActivityProjection.empty(),
            projection_revision=1,
            thread_id="original-session",
        )
        await self.store.cache_activity(
            self.owner, self.identifier, self.message_id, page.to_payload()
        )
        await self.runtime.reconcile(self.owner, self.identifier)
        self.runtime.runner.reset_mock()
        result = await self.runtime.activity(
            self.owner, self.identifier, UUID(self.message["attempt_id"]), 0
        )
        self.assertEqual(result["projection_revision"], 1)
        self.assertTrue(result["closed"])
        self.runtime.runner.assert_not_awaited()

    async def test_completed_session_reaches_native_restart_admission_but_stopped_checkpoint_does_not(
        self,
    ):
        await self.bind()
        await self.runtime.reconcile(self.owner, self.identifier)
        self.assertTrue(await self.store.completed_binding(self.owner, self.identifier))
        following, _ = await self.store.reserve(
            self.owner,
            self.identifier,
            MessageRequest(client_message_id=uuid4(), text="Continue"),
            session_key="fixture",
        )
        new_instance = str(uuid4())
        await self.store.rebind_completed(
            self.owner, self.identifier, UUID(following["id"]), new_instance
        )
        await self.store.observe(
            self.owner,
            self.identifier,
            UUID(following["id"]),
            state="cancelled",
            settled=True,
            thread_id="original-session",
            workspace_hash="sha256:" + "b" * 64,
            reconciled=True,
        )
        self.assertFalse(
            await self.store.completed_binding(self.owner, self.identifier)
        )
