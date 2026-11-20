"""Native approval atomicity and isolation controls using real app storage."""

from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import unittest
from uuid import UUID, uuid4
from unittest.mock import patch
from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import select
from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.models import (
    AssistantConversation,
    AssistantMessage,
    AssistantNativeAction,
    AuthoringContext,
    ConversationRequest,
    MessageRequest,
    NativeCommandRequest,
    NativeActionDecision,
)
from laomedo.integrations.langflow.assistant.persistence import AssistantStore
from laomedo.integrations.langflow.assistant.native import NativeCommands


class NativeApprovalTests(unittest.IsolatedAsyncioTestCase):
    """A human decision and its command reservation are one transaction."""

    async def asyncSetUp(self):
        """Build an owned conversation with one real reserved model response."""
        self.directory = tempfile.TemporaryDirectory()
        self.engine = create_async_engine(
            "sqlite+aiosqlite:///" + (Path(self.directory.name) / "app.db").as_posix()
        )
        self.store = AssistantStore(self.engine)
        await self.store.initialize()
        self.owner, self.key, self.run_id = uuid4(), "session", str(uuid4())
        await self.store.admit_session(self.key, self.owner, time.time() + 1000)
        created = await self.store.create(
            self.owner,
            ConversationRequest(
                connection_id=uuid4(),
                connection_generation=1,
                model="fixture",
                effort="low",
            ),
            session_key=self.key,
        )
        self.conversation = UUID(created["id"])
        message, _ = await self.store.reserve(
            self.owner,
            self.conversation,
            MessageRequest(client_message_id=uuid4(), text="Inspect commands"),
            session_key=self.key,
        )
        self.context = AuthoringContext(
            owner_id=self.owner,
            conversation_id=self.conversation,
            message_id=message["id"],
            attempt_id=message["attempt_id"],
            session_key=self.key,
        )
        await self.store.observe(
            self.owner,
            self.conversation,
            self.context.message_id,
            state="running",
            run_id=self.run_id,
        )
        self.revision = "a" * 64
        self.runtime = SimpleNamespace(
            store=self.store,
            authorize=self.authorize,
            check_session=self.check_session,
            native_catalog=self.catalog,
        )
        self.commands = NativeCommands(self.runtime)
        self.request = NativeCommandRequest(
            name="status", catalog_revision=self.revision, operation_key="status"
        )

    async def asyncTearDown(self):
        """Release only this test's SQLite engine and private directory."""
        await self.engine.dispose()
        self.directory.cleanup()

    async def check_session(self, owner, key):
        """Use real session revocation checks for the inert runtime double."""
        async with self.store.sessions() as session:
            await self.store.authorize(session, owner, key)

    async def authorize(self, context):
        """Validate the exact tool context without granting approval authority."""
        self.assertEqual(context, self.context)
        await self.check_session(context.owner_id, context.session_key)

    async def catalog(self, owner, conversation):
        """Return an inert observed native capability; no provider is called."""
        self.assertEqual((owner, conversation), (self.owner, self.conversation))
        return {
            "state": "available",
            "revision": self.revision,
            "run_id": self.run_id,
            "thread_id": "thread",
            "commands": [
                {
                    "name": "status",
                    "executable": True,
                    "accepts_arguments": False,
                    "may_use_model": False,
                }
            ],
        }

    async def settle(self):
        """Finish the originating response before a human can approve a command."""
        await self.store.observe(
            self.owner,
            self.conversation,
            self.context.message_id,
            state="completed",
            settled=True,
            reconciled=True,
            thread_id="thread",
            workspace_hash="sha256:" + "b" * 64,
        )

    async def test_typed_status_uses_existing_reservation_once_without_model_proposal(
        self,
    ):
        """Explicit human status reserves once; a duplicate never dispatches again."""
        await self.settle()

        async def decide(owner, key, conversation, identifier, decision):
            result, reserved = await self.commands.decide(
                owner, key, conversation, identifier, decision
            )
            self.assertEqual(reserved["text"], "/status")
            return result

        self.runtime.decide_native_action = AsyncMock(side_effect=decide)
        result = await self.commands.submit(
            self.owner, self.key, self.conversation, self.request
        )
        self.assertEqual(result["state"], "executing")
        duplicate = await self.commands.submit(
            self.owner, self.key, self.conversation, self.request
        )
        self.assertEqual(duplicate["result_message_id"], result["result_message_id"])
        self.runtime.decide_native_action.assert_awaited_once()

    async def test_typed_status_without_explicit_non_model_classification_needs_approval(
        self,
    ):
        """Absent provider classification cannot grant the status shortcut."""
        await self.settle()
        catalog = await self.catalog(self.owner, self.conversation)
        catalog["commands"][0].pop("may_use_model")
        self.runtime.native_catalog = AsyncMock(return_value=catalog)
        self.runtime.decide_native_action = AsyncMock()
        result = await self.commands.submit(
            self.owner, self.key, self.conversation, self.request
        )
        self.assertEqual(result["state"], "pending")
        self.runtime.decide_native_action.assert_not_awaited()

    async def test_typed_command_refuses_active_turn_and_revoked_session(self):
        """Human input does not bypass turn serialization or revoked app authority."""
        with self.assertRaisesRegex(AssistantError, "assistant_turn_active"):
            await self.commands.submit(
                self.owner, self.key, self.conversation, self.request
            )
        await self.settle()
        with self.assertRaises(AssistantError):
            await self.commands.submit(
                self.owner, "another-session", self.conversation, self.request
            )

    def decision(self, proposal, value="approve"):
        """Bind a human decision to the exact server proposal digest."""
        return NativeActionDecision(decision=value, digest=proposal["digest"])

    async def test_typed_status_retries_pending_admission_without_duplicate_reservation(
        self,
    ):
        """A failure after proposal retention does not strand typed status behind approval."""
        await self.settle()
        calls = []

        async def decide(owner, key, conversation, identifier, decision):
            calls.append(identifier)
            if len(calls) == 1:
                raise AssistantError("assistant_capacity_busy", 409)
            result, reserved = await self.commands.decide(
                owner, key, conversation, identifier, decision
            )
            self.assertIsNotNone(reserved)
            return result

        self.runtime.decide_native_action = AsyncMock(side_effect=decide)
        with self.assertRaisesRegex(AssistantError, "assistant_capacity_busy"):
            await self.commands.submit(
                self.owner, self.key, self.conversation, self.request
            )
        result = await self.commands.submit(
            self.owner, self.key, self.conversation, self.request
        )
        self.assertEqual(result["state"], "executing")
        duplicate = await self.commands.submit(
            self.owner, self.key, self.conversation, self.request
        )
        self.assertEqual(duplicate["result_message_id"], result["result_message_id"])
        self.assertEqual(calls, [UUID(result["id"])] * 2)

    async def test_approval_waits_for_turn_and_duplicate_decisions_do_not_reserve_again(
        self,
    ):
        """Active-turn refusal preserves the pending proposal; approval reserves once."""
        proposal = await self.commands.propose(self.context, self.request)
        identifier = UUID(proposal["id"])
        with self.assertRaisesRegex(AssistantError, "assistant_turn_active"):
            await self.commands.decide(
                self.owner,
                self.key,
                self.conversation,
                identifier,
                self.decision(proposal),
            )
        await self.settle()
        result, message = await self.commands.decide(
            self.owner, self.key, self.conversation, identifier, self.decision(proposal)
        )
        self.assertEqual(result["state"], "executing")
        self.assertEqual(message["text"], "/status")
        self.assertEqual(message["native_action_id"], proposal["id"])
        again, duplicate = await self.commands.decide(
            self.owner, self.key, self.conversation, identifier, self.decision(proposal)
        )
        self.assertEqual(again["result_message_id"], message["id"])
        self.assertIsNone(duplicate)
        async with self.store.sessions() as session:
            rows = (
                await session.exec(
                    select(AssistantMessage).where(
                        AssistantMessage.conversation_id == self.conversation
                    )
                )
            ).all()
        self.assertEqual(len(rows), 2)
        await self.store.observe(
            self.owner,
            self.conversation,
            UUID(message["id"]),
            state="completed",
            response="Native status",
            settled=True,
            reconciled=True,
            thread_id="thread",
            workspace_hash="sha256:" + "b" * 64,
        )
        result = await self.commands.read(
            self.owner, self.conversation, identifier, session_key=self.key
        )
        self.assertEqual(result["state"], "completed")

    async def test_failed_reservation_rolls_back_action_and_active_message(self):
        """No durable approved gap or orphaned command survives a reservation error."""
        proposal = await self.commands.propose(self.context, self.request)
        await self.settle()
        original = self.store.reserve_message

        async def fail_after_insert(*args, **kwargs):
            """Inject a failure inside the same transaction after the actual insert."""
            await original(*args, **kwargs)
            raise RuntimeError("controlled transaction failure")

        with patch.object(self.store, "reserve_message", side_effect=fail_after_insert):
            with self.assertRaises(RuntimeError):
                await self.commands.decide(
                    self.owner,
                    self.key,
                    self.conversation,
                    UUID(proposal["id"]),
                    self.decision(proposal),
                )
        result = await self.commands.read(
            self.owner, self.conversation, UUID(proposal["id"]), session_key=self.key
        )
        self.assertEqual(result["state"], "pending")
        async with self.store.sessions() as session:
            conversation = await session.get(AssistantConversation, self.conversation)
            rows = (await session.exec(select(AssistantMessage))).all()
        self.assertIsNone(conversation.active_message_id)
        self.assertEqual(len(rows), 1)

    async def test_reject_stale_digest_and_foreign_session_never_reserve(self):
        """Human authority and catalog identity are checked before any command message."""
        proposal = await self.commands.propose(self.context, self.request)
        await self.settle()
        identifier = UUID(proposal["id"])
        with self.assertRaises(AssistantError):
            await self.commands.decide(
                self.owner,
                self.key,
                self.conversation,
                identifier,
                NativeActionDecision(decision="approve", digest="0" * 64),
            )
        await self.store.admit_session("other", self.owner, time.time() + 1000)
        with self.assertRaises(AssistantError):
            await self.commands.decide(
                self.owner,
                "other",
                self.conversation,
                identifier,
                self.decision(proposal),
            )
        result, message = await self.commands.decide(
            self.owner,
            self.key,
            self.conversation,
            identifier,
            self.decision(proposal, "reject"),
        )
        self.assertEqual(result["state"], "rejected")
        self.assertIsNone(message)

    async def test_changed_catalog_refuses_and_retains_stale_receipt(self):
        """An old human-readable command preview cannot authorize a changed catalog."""
        proposal = await self.commands.propose(self.context, self.request)
        await self.settle()
        self.revision = "c" * 64
        result, message = await self.commands.decide(
            self.owner,
            self.key,
            self.conversation,
            UUID(proposal["id"]),
            self.decision(proposal),
        )
        self.assertEqual(result["state"], "stale")
        self.assertIsNone(message)
