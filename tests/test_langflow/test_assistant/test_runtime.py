"""Conversation reconciliation and cancellation controls with real application storage."""

from pathlib import Path
from contextlib import asynccontextmanager
from types import SimpleNamespace
import hashlib
import json
from datetime import datetime, timezone
import tempfile
import time
import unittest
import asyncio
from fastapi import HTTPException
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from langflow.services.database.models.user.model import User
from laomedo.agents.connections.service import ProviderConnections

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
        self.live = False

    def request(self, method, path, body=None):
        self.requests.append((method, path))
        if "/activity?" in path:
            raise AssistantError("activity_journal_unavailable")
        if "/resume/" in path:
            return self.dispatch
        return self.record

    def has_live_session(self, run_id):
        return self.live

    def is_settled(self, run_id):
        return self.settled


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_signed_profile_renewal_preserves_approval_identity_and_logout(self):
        """Use real JWT verification, renewal service and durable revocation rows."""
        import jwt
        from langflow.services.auth.utils import ACCESS_TOKEN_TYPE

        secret = "assistant-session-test-signing-key-32-bytes"
        settings = SimpleNamespace(auth_settings=SimpleNamespace(ALGORITHM="HS256"))
        tokens = [
            jwt.encode(
                {
                    "sub": str(self.owner),
                    "type": ACCESS_TOKEN_TYPE,
                    "exp": time.time() + 1000,
                    "jti": str(uuid4()),
                },
                secret,
                algorithm="HS256",
            )
            for _ in range(4)
        ]
        fingerprints = [hashlib.sha256(value.encode()).hexdigest() for value in tokens]
        requests = [
            SimpleNamespace(headers={"authorization": "Bearer " + value}, cookies={})
            for value in tokens
        ]
        user = SimpleNamespace(id=self.owner)
        service = ProviderConnections(Path(self.directory.name) / "connections")
        self.runtime.provider_connections = service
        try:
            with (
                patch(
                    "langflow.services.deps.get_settings_service", return_value=settings
                ),
                patch(
                    "langflow.services.auth.utils.get_jwt_verification_key",
                    return_value=secret,
                ),
            ):
                root = await self.runtime.session(requests[0], user)
                service.renew_lease(
                    fingerprints[0], fingerprints[1], time.time() + 1000
                )
                self.assertEqual(await self.runtime.session(requests[1], user), root)
                service.close()
                service = ProviderConnections(Path(self.directory.name) / "connections")
                self.runtime.provider_connections = service
                self.assertEqual(await self.runtime.session(requests[1], user), root)
                # This renewal has not visited chat before logout.
                service.renew_lease(
                    fingerprints[1], fingerprints[2], time.time() + 1000
                )
                await self.runtime.lock_session(fingerprints[2])
                service.close()
                service = ProviderConnections(Path(self.directory.name) / "connections")
                self.runtime.provider_connections = service
                self.runtime.revoked_sessions.clear()
                with self.assertRaisesRegex(AssistantError, "assistant_session_locked"):
                    await self.runtime.session(requests[2], user)
                self.assertEqual(
                    await self.runtime.session(requests[3], user), fingerprints[3]
                )
                bad = SimpleNamespace(
                    headers={
                        "authorization": "Bearer "
                        + jwt.encode(
                            {
                                "sub": str(self.owner),
                                "type": ACCESS_TOKEN_TYPE,
                                "exp": time.time() + 1000,
                            },
                            "different-assistant-session-signing-key",
                            algorithm="HS256",
                        )
                    },
                    cookies={},
                )
                with self.assertRaisesRegex(
                    AssistantError, "assistant_native_session_required"
                ):
                    await self.runtime.session(bad, user)
        finally:
            service.close()
            self.runtime.provider_connections = None

    async def test_releasing_claimed_idle_tools_cancels_native_run_once(self):
        await self.bind()
        context = AuthoringContext(
            owner_id=self.owner,
            conversation_id=self.identifier,
            message_id=self.message_id,
            attempt_id=self.message["attempt_id"],
            session_key="fixture",
        )
        registration = SimpleNamespace(registration_id=uuid4())
        client = SimpleNamespace(disconnect=AsyncMock())
        self.runtime.runners[
            self.runtime._runner_key(self.owner, "codex", self.connection_id, 1)
        ] = self.runner
        with patch(
            "laomedo.integrations.langflow.assistant.runtime.McpRegistry.current"
        ) as registry:
            await self.runtime._close_tools(
                context, registration, client, "private", retain=True
            )
            idle = self.runtime.idle_tools.pop(self.identifier)
            self.runtime.claimed_idle_tools[context.message_id] = idle
            await self.runtime._close_tools(context, registration, client, "private")
            await self.runtime._close_tools(context, None, None, "private")
            self.assertEqual(
                self.runner.requests.count(
                    ("POST", "/v1/runs/" + self.run_id + "/cancel")
                ),
                1,
            )
            registry.return_value.release.assert_called_once_with(
                str(registration.registration_id)
            )
            client.disconnect.assert_awaited_once()
            self.assertFalse(self.runtime.claimed_idle_tools)

    async def test_lost_resume_ack_reconciles_existing_attempt_without_reposting(self):
        await self.bind()
        await self.runtime.reconcile(self.owner, self.identifier)
        following, _ = await self.store.reserve(
            self.owner,
            self.identifier,
            MessageRequest(client_message_id=uuid4(), text="Follow up"),
            session_key="fixture",
        )
        self.record["activity_attempt_id"] = following["attempt_id"]
        self.runner.dispatch = {
            "status": "finished",
            "runner_instance_id": self.runner.instance_id,
        }
        self.runner.requests.clear()
        self.assertTrue(await self.runtime.reconcile(self.owner, self.identifier))
        detail = await self.store.detail(self.owner, self.identifier)
        self.assertEqual(detail["messages"][-1]["state"], "completed")
        self.assertEqual(detail["conversation"]["state"], "idle")
        self.assertIn(
            ("GET", "/v1/runs/" + self.run_id + "/resume/" + following["attempt_id"]),
            self.runner.requests,
        )
        self.assertFalse(any(method == "POST" for method, _ in self.runner.requests))
        self.assertFalse(
            any("/v1/requests/" in path for _, path in self.runner.requests)
        )

    async def test_stop_targets_the_saved_conversation_provider(self):
        async with self.store.transaction() as session:
            conversation = await self.store.conversation(
                session, self.owner, self.identifier
            )
            conversation.provider = "claude"
            session.add(conversation)
        await self.bind()
        await self.runtime.stop(
            self.owner, self.identifier, UUID(self.message["attempt_id"])
        )
        self.runtime.runner.assert_awaited_with(
            self.owner, "claude", self.connection_id, 1
        )
        self.assertEqual(
            self.runner.requests[-1], ("POST", "/v1/runs/" + self.run_id + "/cancel")
        )

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

    @asynccontextmanager
    async def empty_lifespan(self, app=None):
        """Keep upstream available while checking assistant-only transition admission."""
        yield None

    async def test_model_catalog_is_reused_only_for_the_same_admitted_runner(self):
        self.runner.request = Mock(
            return_value={
                "provider": "codex",
                "models": [{"id": "fixture", "efforts": ["low"]}],
            }
        )
        args = self.owner, "codex", self.connection_id, 1
        observed = await self.runtime.models(*args)
        self.runner.request.side_effect = AssistantError("provider_connection_busy")
        self.assertEqual(await self.runtime.models(*args), observed)
        request = ConversationRequest(
            connection_id=self.connection_id,
            connection_generation=1,
            model="fixture",
            effort="low",
        )
        first = await self.runtime.create(self.owner, "fixture", request)
        second = await self.runtime.create(self.owner, "fixture", request)
        self.assertNotEqual(first["id"], second["id"])
        self.runner.request.assert_called_once_with("GET", "/v1/models")
        self.runtime.check_connection.side_effect = AssistantError(
            "provider_connection_changed"
        )
        with self.assertRaisesRegex(AssistantError, "provider_connection_changed"):
            await self.runtime.models(*args)
        self.runtime.check_connection.side_effect = None
        self.runner.instance_id = str(uuid4())
        with self.assertRaisesRegex(AssistantError, "provider_connection_busy"):
            await self.runtime.models(*args)
        self.assertEqual(self.runner.request.call_count, 2)

    async def test_unsettled_transition_keeps_app_available_and_marks_old_messages_unknown(
        self,
    ):
        async with self.store.transaction() as session:
            conversation = await self.store.conversation(
                session, self.owner, self.identifier
            )
            conversation.connection_id = None
            conversation.connection_generation = None
            session.add(conversation)
        settings = AssistantSettings(
            app_url="http://127.0.0.1:17881",
            state_root=Path(self.directory.name) / "retired",
        )
        self.runtime.settings = settings
        namespace = hashlib.sha256(settings.app_url.encode()).hexdigest()[:16]
        record = (
            settings.state_root
            / namespace
            / str(self.owner)
            / "runner"
            / "runs"
            / self.run_id
            / "record.json"
        )
        record.parent.mkdir(parents=True)
        record.write_text(json.dumps({"status": "running"}), encoding="utf-8")
        self.runtime.upstream = self.empty_lifespan
        self.runtime.mcp = SimpleNamespace(
            server=SimpleNamespace(
                session_manager=SimpleNamespace(run=self.empty_lifespan)
            )
        )
        with patch(
            "langflow.services.deps.get_db_service",
            return_value=SimpleNamespace(engine=self.engine),
        ):
            async with self.runtime.lifespan(SimpleNamespace(state=SimpleNamespace())):
                self.assertTrue(self.runtime.ready)
                self.assertTrue(self.runtime.migration_blocked)
                with self.assertRaisesRegex(
                    AssistantError, "assistant_reconciliation_required"
                ):
                    AssistantRuntime.check_connection(
                        self.runtime, self.owner, "codex", self.connection_id, 1
                    )
                detail = await self.runtime.store.detail(self.owner, self.identifier)
                self.assertEqual(detail["messages"][0]["state"], "unknown")
                self.assertNotEqual(detail["conversation"]["state"], "running")
                self.runtime.runner.assert_not_awaited()
                self.assertEqual(json.loads(record.read_text()), {"status": "running"})

    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = create_async_engine(
            "sqlite+aiosqlite:///" + (Path(self.directory.name) / "app.db").as_posix()
        )
        async with self.engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)
        self.store = AssistantStore(self.engine)
        self.owner, self.run_id, self.native_id = uuid4(), str(uuid4()), str(uuid4())
        self.connection_id = uuid4()
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
            ConversationRequest(
                connection_id=self.connection_id,
                connection_generation=1,
                model="fixture",
                effort="low",
            ),
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
        self.runtime.check_connection = Mock()

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

    async def test_completed_zero_turn_control_needs_actual_live_ownership_not_cleanup_claims(
        self,
    ):
        await self.bind()
        self.record.update(
            live_session="idle",
            controller_cleanup="retained",
            container_ownership={"cleanup_verified": False},
            turns=[],
            native_command_receipts=[
                {
                    "attempt_id": self.native_id,
                    "status": "completed",
                    "request": {"name": "status"},
                }
            ],
        )
        self.assertFalse(
            await self.runtime.reconcile(
                self.owner, self.identifier, defer_settlement=True
            )
        )
        self.runner.live = True
        self.assertTrue(
            await self.runtime.reconcile(
                self.owner, self.identifier, defer_settlement=True
            )
        )
        self.assertTrue(await self.runtime.reconcile(self.owner, self.identifier))
        detail = await self.store.detail(self.owner, self.identifier)
        self.assertEqual(detail["messages"][0]["state"], "completed")
        self.assertEqual(detail["conversation"]["thread_id"], self.record["thread_id"])
        self.assertEqual(self.record["controller_cleanup"], "retained")
        self.assertFalse(self.record["container_ownership"]["cleanup_verified"])

    async def test_account_removal_reaps_inactive_tools_and_cancels_the_exact_run(self):
        await self.bind()
        context = AuthoringContext(
            owner_id=self.owner,
            conversation_id=self.identifier,
            message_id=self.message_id,
            attempt_id=self.message["attempt_id"],
            session_key="fixture",
        )
        registration = SimpleNamespace(registration_id=uuid4())
        client = SimpleNamespace(disconnect=AsyncMock())
        self.runtime.runners[
            self.runtime._runner_key(self.owner, "codex", self.connection_id, 1)
        ] = self.runner
        registry = Mock()
        with patch(
            "laomedo.integrations.langflow.assistant.runtime.McpRegistry.current",
            return_value=registry,
        ):
            await self.runtime._close_tools(
                context, registration, client, "fixture-inactive-token", retain=True
            )
            self.runtime.check_connection.side_effect = AssistantError(
                "provider_connection_changed", 409
            )
            reaper = asyncio.create_task(self.runtime._reap_idle_tools())
            try:
                for _ in range(40):
                    if self.identifier not in self.runtime.idle_tools:
                        break
                    await asyncio.sleep(0.1)
                self.assertNotIn(self.identifier, self.runtime.idle_tools)
                await asyncio.sleep(0.1)
                self.assertIn(
                    ("POST", "/v1/runs/" + self.run_id + "/cancel"),
                    self.runner.requests,
                )
                registry.release.assert_called_once_with(
                    str(registration.registration_id)
                )
                client.disconnect.assert_awaited_once()
            finally:
                self.runtime.closing = True
                reaper.cancel()
                await asyncio.gather(reaper, return_exceptions=True)

    async def test_refused_delete_does_not_release_idle_native_ownership(self):
        from laomedo.integrations.langflow.assistant.routes import delete_conversation

        await self.bind()
        context = AuthoringContext(
            owner_id=self.owner,
            conversation_id=self.identifier,
            message_id=self.message_id,
            attempt_id=self.message["attempt_id"],
            session_key="fixture",
        )
        registry = Mock()
        client = SimpleNamespace(disconnect=AsyncMock())
        with patch(
            "laomedo.integrations.langflow.assistant.runtime.McpRegistry.current",
            return_value=registry,
        ):
            await self.runtime._close_tools(
                context,
                SimpleNamespace(registration_id=uuid4()),
                client,
                "fixture-inactive-token",
                retain=True,
            )
            held = self.runtime.idle_tools[self.identifier]
            with self.assertRaises(HTTPException) as refusal:
                await delete_conversation(
                    self.identifier, context=(self.runtime, self.owner, "fixture")
                )
            self.assertEqual(refusal.exception.status_code, 409)
            self.assertIs(self.runtime.idle_tools[self.identifier], held)
            registry.release.assert_not_called()
            client.disconnect.assert_not_awaited()
            self.assertEqual(self.runner.requests, [])

    async def test_retained_tools_are_inactive_and_old_cleanup_cannot_revoke_the_next_message(
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
        registration = SimpleNamespace(registration_id=uuid4())
        client = SimpleNamespace(disconnect=AsyncMock())
        token = "fixture-private-endpoint"
        self.runtime.contexts[context.message_id] = context
        self.runtime.host_tokens[token] = context
        registry = Mock()
        with patch(
            "laomedo.integrations.langflow.assistant.runtime.McpRegistry.current",
            return_value=registry,
        ):
            await self.runtime._close_tools(
                context, registration, client, token, retain=True
            )
            self.assertNotIn(token, self.runtime.host_tokens)
            self.assertNotIn(context.message_id, self.runtime.contexts)
            registry.release.assert_not_called()
            client.disconnect.assert_not_awaited()
            idle = self.runtime.idle_tools[self.identifier]
            following = context.model_copy(
                update={"message_id": uuid4(), "attempt_id": uuid4()}
            )
            self.assertTrue(idle.matches(following))
            self.assertFalse(
                idle.matches(
                    following.model_copy(update={"session_key": "other-browser"})
                )
            )
            self.runtime.host_tokens[token] = following
            await self.runtime._close_tools(context, None, None, token)
            self.assertIs(self.runtime.host_tokens[token], following)
            await self.runtime.release_idle_session(self.owner, self.identifier)
            registry.release.assert_called_once_with(str(registration.registration_id))
            client.disconnect.assert_awaited_once()
            self.assertNotIn(self.identifier, self.runtime.idle_tools)

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
