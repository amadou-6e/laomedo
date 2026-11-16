"""Atomic owner-scoped assistant state in the application's existing database."""

from contextlib import asynccontextmanager
import hashlib
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.models import (
    AssistantConversation,
    AssistantMessage,
    AssistantDraftReceipt,
    AssistantSession,
)


class AssistantStore:
    """Serialize reservations and keep retained history bounded on every read."""

    def __init__(self, engine):
        """Use the existing app engine, not a parallel workflow database."""
        self.engine = engine
        self.sessions = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

    async def initialize(self):
        """Create only this feature's owned tables after upstream migrations."""
        tables = [
            model.__table__
            for model in (
                AssistantConversation,
                AssistantMessage,
                AssistantDraftReceipt,
                AssistantSession,
            )
        ]
        async with self.engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all, tables=tables)

    @asynccontextmanager
    async def transaction(self):
        """Take SQLite's writer lock before reads; PostgreSQL consumers also lock rows."""
        async with self.sessions() as session:
            try:
                if self.engine.dialect.name == "sqlite":
                    await session.exec(text("BEGIN IMMEDIATE"))
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    async def conversation(self, session, owner, identifier, *, lock=False):
        """Read one owner-scoped row, optionally retaining its transaction lock."""
        statement = select(AssistantConversation).where(
            AssistantConversation.id == identifier,
            AssistantConversation.owner_id == owner,
        )
        if lock:
            statement = statement.with_for_update()
        value = (await session.exec(statement)).first()
        if value is None:
            raise AssistantError("assistant_conversation_not_found", 404)
        return value

    async def admit_session(self, key, owner, expires_at):
        """Retain a validated session; a revoked bearer cannot resurrect itself."""
        async with self.transaction() as session:
            row = await session.get(AssistantSession, key)
            if row is not None:
                if (
                    row.revoked
                    or row.owner_id != owner
                    or row.expires_at <= time.time()
                ):
                    raise AssistantError("assistant_session_locked", 403)
                return
            if expires_at <= time.time():
                raise AssistantError("assistant_session_locked", 403)
            session.add(
                AssistantSession(key=key, owner_id=owner, expires_at=expires_at)
            )

    async def authorize(self, session, owner, key):
        """Lock the revocation fence in the same transaction as a save/reservation."""
        row = (
            await session.exec(
                select(AssistantSession)
                .where(AssistantSession.key == key)
                .with_for_update()
            )
        ).first()
        if (
            row is None
            or row.owner_id != owner
            or row.revoked
            or row.expires_at <= time.time()
        ):
            raise AssistantError("assistant_session_locked", 403)

    async def revoke(self, key):
        """Persist lock/sign-out under the same writer discipline as draft saves."""
        async with self.transaction() as session:
            row = await session.get(AssistantSession, key)
            if row:
                row.revoked = True
                session.add(row)

    async def create(self, owner, request):
        """Persist model selection and optional owner-visible predecessor without inference."""
        async with self.transaction() as session:
            if request.linked_conversation_id:
                await self.conversation(session, owner, request.linked_conversation_id)
            conversation = AssistantConversation(owner_id=owner, **request.model_dump())
            session.add(conversation)
            await session.flush()
            return conversation.model_dump(mode="json")

    async def list(self, owner, cursor=0):
        """Return a bounded page without message bodies or other owners' summaries."""
        async with self.sessions() as session:
            rows = (
                await session.exec(
                    select(AssistantConversation)
                    .where(AssistantConversation.owner_id == owner)
                    .order_by(
                        AssistantConversation.updated_at.desc(),
                        AssistantConversation.id,
                    )
                    .offset(cursor)
                    .limit(31)
                )
            ).all()
            return {
                "conversations": [row.model_dump(mode="json") for row in rows[:30]],
                "next_cursor": cursor + 30 if len(rows) > 30 else None,
            }

    async def detail(self, owner, identifier, cursor=0):
        """Read retained messages and authoritative receipts, never model save claims."""
        async with self.sessions() as session:
            conversation = await self.conversation(session, owner, identifier)
            messages = (
                await session.exec(
                    select(AssistantMessage)
                    .where(AssistantMessage.conversation_id == identifier)
                    .order_by(AssistantMessage.created_at.desc(), AssistantMessage.id)
                    .offset(cursor)
                    .limit(31)
                )
            ).all()
            receipts = (
                await session.exec(
                    select(AssistantDraftReceipt)
                    .where(
                        AssistantDraftReceipt.conversation_id == identifier,
                        AssistantDraftReceipt.owner_id == owner,
                    )
                    .order_by(AssistantDraftReceipt.created_at.desc())
                    .limit(50)
                )
            ).all()
            return {
                "conversation": conversation.model_dump(mode="json"),
                "messages": [
                    row.model_dump(mode="json", exclude={"digest"})
                    for row in reversed(messages[:30])
                ],
                "next_cursor": cursor + 30 if len(messages) > 30 else None,
                "drafts": [
                    row.model_dump(mode="json", exclude={"digest", "owner_id"})
                    for row in receipts
                ],
            }

    async def reserve(self, owner, identifier, request, *, session_key):
        """Reserve once before native/MCP effects; conflicting keys never overwrite."""
        digest = hashlib.sha256(request.text.encode()).hexdigest()
        async with self.transaction() as session:
            await self.authorize(session, owner, session_key)
            conversation = await self.conversation(
                session, owner, identifier, lock=True
            )
            prior = (
                await session.exec(
                    select(AssistantMessage).where(
                        AssistantMessage.conversation_id == identifier,
                        AssistantMessage.client_message_id == request.client_message_id,
                    )
                )
            ).first()
            if prior:
                if prior.digest != digest:
                    raise AssistantError("assistant_message_conflict")
                return prior.model_dump(mode="json", exclude={"digest"}), False
            if conversation.active_message_id is not None:
                raise AssistantError("assistant_turn_active")
            if conversation.state == "attention":
                raise AssistantError(
                    conversation.error_code or "assistant_continuation_unavailable"
                )
            message = AssistantMessage(
                conversation_id=identifier,
                client_message_id=request.client_message_id,
                digest=digest,
                text=request.text,
            )
            conversation.active_message_id = message.id
            conversation.state = "starting"
            if conversation.title == "New conversation":
                conversation.title = request.text[:80]
            conversation.updated_at = time.time()
            session.add(message)
            session.add(conversation)
            await session.flush()
            return message.model_dump(mode="json", exclude={"digest"}), True

    async def message(self, owner, conversation_id, message_id):
        """Read a message only after checking its authenticated conversation owner."""
        async with self.sessions() as session:
            conversation = await self.conversation(session, owner, conversation_id)
            message = await session.get(AssistantMessage, message_id)
            if message is None or message.conversation_id != conversation.id:
                raise AssistantError("assistant_message_not_found", 404)
            return conversation, message

    async def observe(
        self,
        owner,
        conversation_id,
        message_id,
        *,
        run_id=None,
        native_attempt_id=None,
        instance_id=None,
        state=None,
        response=None,
        error=None,
        thread_id=None,
        workspace_hash=None,
        settled=False,
    ):
        """Retain observations for the exact reserved message; settlement never replays it."""
        async with self.transaction() as session:
            conversation = await self.conversation(
                session, owner, conversation_id, lock=True
            )
            message = await session.get(AssistantMessage, message_id)
            if message is None or message.conversation_id != conversation.id:
                raise AssistantError("assistant_message_not_found", 404)
            if run_id:
                if conversation.run_id not in (None, run_id) or message.run_id not in (
                    None,
                    run_id,
                ):
                    raise AssistantError("assistant_native_identity_mismatch")
                conversation.run_id = message.run_id = run_id
            if native_attempt_id:
                if message.native_attempt_id not in (None, native_attempt_id):
                    raise AssistantError("assistant_native_identity_mismatch")
                message.native_attempt_id = native_attempt_id
            if instance_id:
                if conversation.runner_instance_id not in (None, instance_id):
                    raise AssistantError("assistant_runner_restarted")
                conversation.runner_instance_id = instance_id
            if state:
                message.state = state
            if response is not None:
                message.response = response[:100000]
            message.error_code = error
            if conversation.active_message_id == message.id:
                conversation.state = (
                    "reconciling" if state == "unknown" else state or conversation.state
                )
                conversation.error_code = error
                if settled:
                    conversation.active_message_id = None
                    conversation.thread_id = thread_id
                    conversation.workspace_hash = workspace_hash
                    conversation.state = (
                        "idle" if thread_id and workspace_hash else "attention"
                    )
                    conversation.error_code = (
                        error if conversation.state == "attention" else None
                    )
                    if (
                        conversation.state == "attention"
                        and not conversation.error_code
                    ):
                        conversation.error_code = "assistant_continuation_unavailable"
            conversation.updated_at = time.time()
            session.add(message)
            session.add(conversation)

    async def pending(self):
        """Read active reservations for restart reconciliation without dispatching them."""
        async with self.sessions() as session:
            return (
                await session.exec(
                    select(AssistantConversation)
                    .where(AssistantConversation.active_message_id.is_not(None))
                    .limit(100)
                )
            ).all()
