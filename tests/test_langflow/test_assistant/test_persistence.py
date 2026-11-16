"""Real SQLite reservations, owner isolation, retained history and session revocation."""

import asyncio
from pathlib import Path
import tempfile
import time
import unittest
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import create_async_engine

from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.models import (
    ConversationRequest,
    ConversationRenameRequest,
    MessageRequest,
)
from laomedo.integrations.langflow.assistant.persistence import AssistantStore


class PersistenceTests(unittest.IsolatedAsyncioTestCase):
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
