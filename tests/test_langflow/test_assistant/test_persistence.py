"""Real SQLite reservations, owner isolation, retained history and session revocation."""

import asyncio
from pathlib import Path
import tempfile
import time
import unittest
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import select

from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.models import (
    ConversationRequest,
    ConversationRenameRequest,
    MessageRequest,
    AssistantConversation,
    AssistantMessage,
    AssistantDraftReceipt,
    AssistantGraphAction,
    AssistantGraphPermission,
)
from laomedo.integrations.langflow.assistant.persistence import AssistantStore


class StartupSchemaTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_app_gets_only_owned_tables_before_shared_schema_check(self):
        """Optional feature startup preserves auth rows and leaves fresh DBs alone."""
        from sqlalchemy import inspect

        with tempfile.TemporaryDirectory() as directory:
            engine = create_async_engine(
                "sqlite+aiosqlite:///" + str(Path(directory) / "state.db")
            )
            try:
                store = AssistantStore(engine)
                await store.upgrade_retained()
                async with engine.begin() as connection:
                    names = await connection.run_sync(
                        lambda conn: inspect(conn).get_table_names()
                    )
                    self.assertEqual(names, [])
                    await connection.exec_driver_sql(
                        'CREATE TABLE "user" (id TEXT PRIMARY KEY, marker TEXT)'
                    )
                    await connection.exec_driver_sql(
                        "INSERT INTO user VALUES ('owned-profile', 'retained')"
                    )
                    await connection.exec_driver_sql(
                        "CREATE TABLE laomedo_assistant_message (id TEXT PRIMARY KEY)"
                    )
                await store.upgrade_retained()
                async with engine.begin() as connection:
                    names = await connection.run_sync(
                        lambda conn: inspect(conn).get_table_names()
                    )
                    self.assertEqual(
                        set(names),
                        {
                            "user",
                            "laomedo_assistant_conversation",
                            "laomedo_assistant_message",
                            "laomedo_assistant_draft_receipt",
                            "laomedo_assistant_session",
                            "laomedo_assistant_graph_action",
                            "laomedo_assistant_graph_permission",
                            "laomedo_assistant_native_action",
                        },
                    )
                    rows = (
                        await connection.exec_driver_sql(
                            'SELECT id, marker FROM "user"'
                        )
                    ).all()
                    self.assertEqual(rows, [("owned-profile", "retained")])
                    columns = await connection.run_sync(
                        lambda conn: {
                            column["name"]
                            for column in inspect(conn).get_columns(
                                "laomedo_assistant_message"
                            )
                        }
                    )
                    self.assertIn("initial_native_command", columns)
            finally:
                await engine.dispose()


class PersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_initial_status_is_durable_and_bound_to_message_identity(self):
        """Initial control intent survives history reads and cannot alias ordinary chat."""
        request = MessageRequest(
            client_message_id=uuid4(), text="/status", initial_native_command="status"
        )
        message, created = await self.store.reserve(
            self.owner, self.identifier, request, session_key=self.key
        )
        self.assertTrue(created)
        self.assertEqual(message["initial_native_command"], "status")
        duplicate, created = await self.store.reserve(
            self.owner, self.identifier, request, session_key=self.key
        )
        self.assertFalse(created)
        self.assertEqual(duplicate["id"], message["id"])
        with self.assertRaisesRegex(AssistantError, "assistant_message_conflict"):
            await self.store.reserve(
                self.owner,
                self.identifier,
                MessageRequest(
                    client_message_id=request.client_message_id, text="/status"
                ),
                session_key=self.key,
            )
        detail = await self.store.detail(self.owner, self.identifier)
        self.assertEqual(detail["messages"][0]["initial_native_command"], "status")

    async def test_other_providers_refuse_initial_status_before_reserving(self):
        """Codex's initial control mode cannot become a Claude or OpenCode prompt."""
        for provider in ("claude", "opencode"):
            conversation = await self.store.create(
                self.owner,
                ConversationRequest(provider=provider, model="fixture", effort="low"),
                session_key=self.key,
            )
            with (
                self.subTest(provider=provider),
                self.assertRaisesRegex(
                    AssistantError, "native_command_context_invalid"
                ),
            ):
                await self.store.reserve(
                    self.owner,
                    UUID(conversation["id"]),
                    MessageRequest(
                        client_message_id=uuid4(),
                        text="/status",
                        initial_native_command="status",
                    ),
                    session_key=self.key,
                )
            detail = await self.store.detail(self.owner, UUID(conversation["id"]))
            self.assertEqual(detail["messages"], [])

    async def test_delete_removes_owned_chat_records_and_clears_successor_link(self):
        """Deleting a settled chat removes its private receipts and remembered grants."""
        message, _ = await self.store.reserve(
            self.owner,
            self.identifier,
            MessageRequest(client_message_id=uuid4(), text="Hello"),
            session_key=self.key,
        )
        await self.store.observe(
            self.owner,
            self.identifier,
            UUID(message["id"]),
            state="completed",
            settled=True,
            reconciled=True,
        )
        successor = await self.store.create(
            self.owner,
            ConversationRequest(
                model="fixture", effort="low", linked_conversation_id=self.identifier
            ),
            session_key=self.key,
        )
        action_id, flow = uuid4(), uuid4()
        async with self.store.transaction() as session:
            session.add(
                AssistantDraftReceipt(
                    owner_id=self.owner,
                    conversation_id=self.identifier,
                    message_id=UUID(message["id"]),
                    attempt_id=UUID(message["attempt_id"]),
                    draft_key="draft",
                    digest="digest",
                    workflow_id=flow,
                    name="Saved flow",
                    revision="revision",
                )
            )
            session.add(
                AssistantGraphAction(
                    id=action_id,
                    owner_id=self.owner,
                    conversation_id=self.identifier,
                    message_id=UUID(message["id"]),
                    attempt_id=UUID(message["attempt_id"]),
                    session_key=self.key,
                    operation_key="proposal",
                    workflow_id=flow,
                    name="Saved flow",
                    kind="edit",
                    digest="digest",
                    request={},
                    preview=[],
                    revision="revision",
                    expires_at=time.time() + 100,
                )
            )
            session.add(
                AssistantGraphPermission(
                    owner_id=self.owner,
                    conversation_id=self.identifier,
                    session_key=self.key,
                    category="edit",
                    action_id=action_id,
                )
            )
        other_owner = uuid4()
        await self.store.admit_session(
            "other-owner-session", other_owner, time.time() + 100
        )
        with self.assertRaisesRegex(AssistantError, "assistant_conversation_not_found"):
            await self.store.delete_conversation(
                other_owner, self.identifier, session_key="other-owner-session"
            )
        self.assertEqual(
            await self.store.delete_conversation(
                self.owner, self.identifier, session_key=self.key
            ),
            {"state": "deleted"},
        )
        async with self.store.sessions() as session:
            self.assertIsNone(await session.get(AssistantConversation, self.identifier))
            for model in (
                AssistantMessage,
                AssistantDraftReceipt,
                AssistantGraphAction,
                AssistantGraphPermission,
            ):
                self.assertEqual(
                    (
                        await session.exec(
                            select(model).where(
                                model.conversation_id == self.identifier
                            )
                        )
                    ).all(),
                    [],
                )
        retained = await self.store.detail(self.owner, UUID(successor["id"]))
        self.assertIsNone(retained["conversation"]["linked_conversation_id"])
        with self.assertRaisesRegex(AssistantError, "assistant_conversation_not_found"):
            await self.store.detail(self.owner, self.identifier)

    async def test_delete_refuses_active_work_and_revoked_sessions(self):
        """Never discard an active response or an admitted workflow execution."""
        message, _ = await self.store.reserve(
            self.owner,
            self.identifier,
            MessageRequest(client_message_id=uuid4(), text="Hello"),
            session_key=self.key,
        )
        with self.assertRaisesRegex(AssistantError, "assistant_conversation_active"):
            await self.store.delete_conversation(
                self.owner, self.identifier, session_key=self.key
            )
        await self.store.observe(
            self.owner,
            self.identifier,
            UUID(message["id"]),
            state="completed",
            settled=True,
            reconciled=True,
        )
        async with self.store.transaction() as session:
            action = AssistantGraphAction(
                owner_id=self.owner,
                conversation_id=self.identifier,
                message_id=UUID(message["id"]),
                attempt_id=UUID(message["attempt_id"]),
                session_key=self.key,
                operation_key="run",
                workflow_id=uuid4(),
                name="Graph",
                kind="run",
                digest="digest",
                request={},
                preview=[],
                revision="revision",
                state="executing",
                expires_at=time.time() + 100,
            )
            session.add(action)
        with self.assertRaisesRegex(AssistantError, "assistant_conversation_active"):
            await self.store.delete_conversation(
                self.owner, self.identifier, session_key=self.key
            )
        async with self.store.transaction() as session:
            row = await session.get(AssistantGraphAction, action.id)
            row.state = "succeeded"
            session.add(row)
        await self.store.revoke(self.key)
        with self.assertRaisesRegex(AssistantError, "assistant_session_locked"):
            await self.store.delete_conversation(
                self.owner, self.identifier, session_key=self.key
            )

    async def test_concurrent_send_and_delete_never_leave_an_orphan_reservation(self):
        """Exactly one admission wins the conversation's deletion/reservation race."""
        results = await asyncio.gather(
            self.store.delete_conversation(
                self.owner, self.identifier, session_key=self.key
            ),
            self.store.reserve(
                self.owner,
                self.identifier,
                MessageRequest(client_message_id=uuid4(), text="Race"),
                session_key=self.key,
            ),
            return_exceptions=True,
        )
        async with self.store.sessions() as session:
            chat = await session.get(AssistantConversation, self.identifier)
            messages = (
                await session.exec(
                    select(AssistantMessage).where(
                        AssistantMessage.conversation_id == self.identifier
                    )
                )
            ).all()
        if chat is None:
            self.assertEqual(messages, [])
            self.assertIsInstance(results[1], AssistantError)
        else:
            self.assertEqual(len(messages), 1)
            self.assertEqual(chat.active_message_id, messages[0].id)
            self.assertIsInstance(results[0], AssistantError)

    async def test_rename_is_retained_and_owner_session_scoped(self):
        """Titles persist without a message or execution; other owners cannot rename."""
        request = ConversationRenameRequest(title="My workflow assistant")
        with self.assertRaises(AssistantError):
            await self.store.rename(
                uuid4(), self.identifier, request, session_key=self.key
            )
        renamed = await self.store.rename(
            self.owner, self.identifier, request, session_key=self.key
        )
        self.assertEqual(renamed["title"], request.title)
        detail = await AssistantStore(self.engine).detail(self.owner, self.identifier)
        self.assertEqual(detail["conversation"]["title"], request.title)
        self.assertEqual(detail["messages"], [])
        self.assertIsNone(detail["conversation"]["run_id"])
        await self.store.revoke(self.key)
        with self.assertRaises(AssistantError):
            await self.store.rename(
                self.owner, self.identifier, request, session_key=self.key
            )

    async def test_turn_selection_is_immutable_and_part_of_retry_identity(self):
        """A retry cannot silently change models; a following turn can choose another."""
        request = MessageRequest(
            client_message_id=uuid4(), text="Create", model="first", effort="low"
        )
        first, created = await self.store.reserve(
            self.owner, self.identifier, request, session_key=self.key
        )
        self.assertTrue(created)
        self.assertEqual((first["model"], first["effort"]), ("first", "low"))
        with self.assertRaisesRegex(AssistantError, "assistant_message_conflict"):
            await self.store.submitted(
                self.owner,
                self.identifier,
                request.model_copy(update={"effort": "high"}),
            )
        await self.store.observe(
            self.owner,
            self.identifier,
            UUID(first["id"]),
            state="completed",
            thread_id="native-thread",
            workspace_hash="sha256:" + "a" * 64,
            settled=True,
            reconciled=True,
        )
        second, _ = await self.store.reserve(
            self.owner,
            self.identifier,
            MessageRequest(
                client_message_id=uuid4(),
                text="Continue",
                model="second",
                effort="high",
            ),
            session_key=self.key,
        )
        retained = await self.store.submitted(self.owner, self.identifier, request)
        self.assertEqual((retained["model"], retained["effort"]), ("first", "low"))
        self.assertEqual((second["model"], second["effort"]), ("second", "high"))
        detail = await AssistantStore(self.engine).detail(self.owner, self.identifier)
        self.assertEqual(detail["conversation"]["model"], "second")
        self.assertEqual(detail["conversation"]["effort"], "high")

    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = create_async_engine(
            "sqlite+aiosqlite:///" + (Path(self.directory.name) / "app.db").as_posix()
        )
        self.store = AssistantStore(self.engine)
        await self.store.initialize()
        self.owner = uuid4()
        self.key = "fixture-session-hash"
        await self.store.admit_session(self.key, self.owner, time.time() + 1000)
        self.conversation = await self.store.create(
            self.owner,
            ConversationRequest(model="fixture", effort="low"),
            session_key=self.key,
        )
        self.identifier = UUID(self.conversation["id"])

    async def asyncTearDown(self):
        await self.engine.dispose()
        self.directory.cleanup()

    async def test_duplicate_concurrent_messages_share_one_reservation(self):
        request = MessageRequest(client_message_id=uuid4(), text="Create a draft")
        results = await asyncio.gather(
            *(
                self.store.reserve(
                    self.owner, self.identifier, request, session_key=self.key
                )
                for _ in range(5)
            )
        )
        self.assertEqual(sum(created for _, created in results), 1)
        self.assertEqual(len({message["id"] for message, _ in results}), 1)
        self.assertEqual(
            len((await self.store.detail(self.owner, self.identifier))["messages"]), 1
        )
        with self.assertRaisesRegex(AssistantError, "assistant_message_conflict"):
            await self.store.reserve(
                self.owner,
                self.identifier,
                request.model_copy(update={"text": "Different"}),
                session_key=self.key,
            )
        with self.assertRaisesRegex(AssistantError, "assistant_turn_active"):
            await self.store.reserve(
                self.owner,
                self.identifier,
                request.model_copy(update={"client_message_id": uuid4()}),
                session_key=self.key,
            )

    async def test_owner_cannot_read_or_reserve_another_conversation(self):
        other = uuid4()
        await self.store.admit_session("other-key", other, time.time() + 1000)
        self.assertEqual((await self.store.list(other))["conversations"], [])
        with self.assertRaisesRegex(AssistantError, "assistant_conversation_not_found"):
            await self.store.detail(other, self.identifier)
        with self.assertRaisesRegex(AssistantError, "assistant_conversation_not_found"):
            await self.store.reserve(
                other,
                self.identifier,
                MessageRequest(client_message_id=uuid4(), text="read"),
                session_key="other-key",
            )

    async def test_reopen_retains_unknown_attempt_and_cannot_replay_it(self):
        request = MessageRequest(client_message_id=uuid4(), text="Persist this message")
        message, _ = await self.store.reserve(
            self.owner, self.identifier, request, session_key=self.key
        )
        await self.store.observe(
            self.owner,
            self.identifier,
            UUID(message["id"]),
            state="unknown",
            error="assistant_dispatch_unknown",
        )
        reopened = AssistantStore(self.engine)
        result, created = await reopened.reserve(
            self.owner, self.identifier, request, session_key=self.key
        )
        self.assertFalse(created)
        self.assertEqual(result["state"], "unknown")
        detail = await reopened.detail(self.owner, self.identifier)
        self.assertEqual(detail["conversation"]["state"], "reconciling")
        self.assertEqual(detail["messages"][0]["text"], request.text)

    async def test_revoked_session_cannot_readmit_or_reserve(self):
        await self.store.revoke(self.key)
        with self.assertRaisesRegex(AssistantError, "assistant_session_locked"):
            await self.store.admit_session(self.key, self.owner, time.time() + 2000)
        with self.assertRaisesRegex(AssistantError, "assistant_session_locked"):
            await self.store.reserve(
                self.owner,
                self.identifier,
                MessageRequest(client_message_id=uuid4(), text="never dispatched"),
                session_key=self.key,
            )
        with self.assertRaisesRegex(AssistantError, "assistant_session_locked"):
            await self.store.create(
                self.owner,
                ConversationRequest(model="fixture", effort="low"),
                session_key=self.key,
            )

    async def test_restart_before_any_binding_cannot_silently_bind_new_session(self):
        message, _ = await self.store.reserve(
            self.owner,
            self.identifier,
            MessageRequest(client_message_id=uuid4(), text="Unobserved dispatch"),
            session_key=self.key,
        )
        identifier = UUID(message["id"])
        with self.assertRaisesRegex(AssistantError, "assistant_observation_invalid"):
            await self.store.observe(
                self.owner, self.identifier, identifier, state="completed"
            )
        await self.store.observe(
            self.owner,
            self.identifier,
            identifier,
            instance_id=str(uuid4()),
            state="unknown",
            settled=True,
            reconciled=True,
            error="assistant_runner_restarted",
            thread_id="must-not-bind",
            workspace_hash="sha256:" + "a" * 64,
        )
        detail = await self.store.detail(self.owner, self.identifier)
        self.assertEqual(detail["conversation"]["state"], "attention")
        self.assertIsNone(detail["conversation"]["runner_instance_id"])
        self.assertIsNone(detail["conversation"]["thread_id"])
        self.assertIsNone(detail["conversation"]["workspace_hash"])

    async def test_metadata_poll_preserves_unknown_reason_and_terminal_state_cannot_regress(
        self,
    ):
        message, _ = await self.store.reserve(
            self.owner,
            self.identifier,
            MessageRequest(client_message_id=uuid4(), text="Keep identity"),
            session_key=self.key,
        )
        identifier = UUID(message["id"])
        await self.store.observe(
            self.owner,
            self.identifier,
            identifier,
            state="unknown",
            error="assistant_dispatch_unknown",
        )
        await self.store.observe(
            self.owner, self.identifier, identifier, run_id=str(uuid4())
        )
        detail = await self.store.detail(self.owner, self.identifier)
        self.assertEqual(
            detail["messages"][0]["error_code"], "assistant_dispatch_unknown"
        )
        self.assertEqual(
            detail["conversation"]["error_code"], "assistant_dispatch_unknown"
        )
        with self.assertRaisesRegex(
            AssistantError, "assistant_reconciliation_required"
        ):
            await self.store.observe(
                self.owner,
                self.identifier,
                identifier,
                state="completed",
                settled=True,
                thread_id="thread",
                workspace_hash="sha256:" + "a" * 64,
            )
        await self.store.observe(
            self.owner,
            self.identifier,
            identifier,
            state="completed",
            settled=True,
            reconciled=True,
            thread_id="thread",
            workspace_hash="sha256:" + "a" * 64,
        )
        await self.store.observe(
            self.owner, self.identifier, identifier, state="running"
        )
        detail = await self.store.detail(self.owner, self.identifier)
        self.assertEqual(detail["messages"][0]["state"], "completed")
        self.assertEqual(detail["conversation"]["state"], "idle")

    async def test_restart_reconciliation_settles_attention_without_rebinding_or_replay(
        self,
    ):
        message, _ = await self.store.reserve(
            self.owner,
            self.identifier,
            MessageRequest(client_message_id=uuid4(), text="Before restart"),
            session_key=self.key,
        )
        identifier = UUID(message["id"])
        original, restarted = str(uuid4()), str(uuid4())
        await self.store.observe(
            self.owner,
            self.identifier,
            identifier,
            instance_id=original,
            state="running",
        )
        with self.assertRaisesRegex(AssistantError, "assistant_runner_restarted"):
            await self.store.observe(
                self.owner,
                self.identifier,
                identifier,
                instance_id=restarted,
                state="running",
            )
        await self.store.observe(
            self.owner,
            self.identifier,
            identifier,
            instance_id=restarted,
            state="unknown",
            settled=True,
            reconciled=True,
            error="assistant_runner_restarted",
            thread_id="never-rebind",
            workspace_hash="sha256:" + "a" * 64,
        )
        detail = await self.store.detail(self.owner, self.identifier)
        self.assertEqual(detail["conversation"]["state"], "attention")
        self.assertEqual(detail["conversation"]["runner_instance_id"], original)
        self.assertIsNone(detail["conversation"]["active_message_id"])
        self.assertIsNone(detail["conversation"]["workspace_hash"])
