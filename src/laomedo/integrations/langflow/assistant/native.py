"""Conversation-bound native command proposals and atomic human admission."""

import time
from uuid import UUID
from sqlmodel import select
from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.models import (
    AssistantMessage,
    AssistantNativeAction,
    MessageRequest,
    NativeCommandRequest,
    NativeActionDecision,
)


class NativeCommands:
    """Use the existing chat transaction and dispatch owners, never a second runner."""

    def __init__(self, runtime):
        """Bind app-owned persistence, session authority and current native catalog."""
        self.runtime, self.store = runtime, runtime.store

    async def submit(self, owner, key, conversation_id, request):
        """Retain a human-entered command; only Codex status skips a second approval."""
        await self.runtime.check_session(owner, key)
        catalog = await self.runtime.native_catalog(owner, conversation_id)
        async with self.store.transaction() as session:
            await self.store.authorize(session, owner, key)
            conversation = await self.store.conversation(
                session, owner, conversation_id, lock=True
            )
            prior = (
                await session.exec(
                    select(AssistantNativeAction).where(
                        AssistantNativeAction.conversation_id == conversation_id,
                        AssistantNativeAction.operation_key == request.operation_key,
                    )
                )
            ).first()
            if prior is not None:
                if prior.digest != request.digest() or prior.session_key != key:
                    raise AssistantError("assistant_action_conflict", 409)
                if prior.state != "pending":
                    return prior.public(session_key=key)
            if (
                conversation.active_message_id is not None
                or conversation.state != "idle"
            ):
                raise AssistantError("assistant_turn_active", 409)
            if (
                catalog.get("revision") != request.catalog_revision
                or catalog.get("run_id") != conversation.run_id
                or not conversation.thread_id
                or catalog.get("thread_id") != conversation.thread_id
            ):
                raise AssistantError("native_command_catalog_changed", 409)
            selected = next(
                (
                    item
                    for item in catalog.get("commands", [])
                    if item["name"] == request.name and item["executable"]
                ),
                None,
            )
            if selected is None or (
                request.arguments and not selected["accepts_arguments"]
            ):
                raise AssistantError("native_command_not_available", 409)
            row = prior
            if row is None:
                message = (
                    await session.exec(
                        select(AssistantMessage)
                        .where(AssistantMessage.conversation_id == conversation_id)
                        .order_by(AssistantMessage.created_at.desc())
                        .limit(1)
                    )
                ).first()
                if message is None:
                    raise AssistantError("native_command_not_available", 409)
                row = AssistantNativeAction(
                    owner_id=owner,
                    conversation_id=conversation_id,
                    message_id=message.id,
                    session_key=key,
                    operation_key=request.operation_key,
                    digest=request.digest(),
                    request=request.model_dump(mode="json"),
                    run_id=conversation.run_id,
                    thread_id=conversation.thread_id,
                    expires_at=time.time() + 900,
                )
                session.add(row)
                await session.flush()
            result = row.public(session_key=key)
            immediate = (
                conversation.provider == "codex"
                and request.name == "status"
                and not request.arguments
                and selected.get("may_use_model") is False
            )
        if immediate:
            # Reuse the same atomic reservation, identity checks and dispatch owner.
            # The MCP proposal path never calls this human-only method.
            return await self.runtime.decide_native_action(
                owner,
                key,
                conversation_id,
                row.id,
                NativeActionDecision(decision="approve", digest=request.digest()),
            )
        return result

    async def propose(self, context, request):
        """Retain an exact built-in proposal without native dispatch or approval."""
        await self.runtime.authorize(context)
        catalog = await self.runtime.native_catalog(
            context.owner_id, context.conversation_id
        )
        if catalog.get("revision") != request.catalog_revision or not any(
            item["name"] == request.name and item["executable"]
            for item in catalog.get("commands", [])
        ):
            raise AssistantError("native_command_catalog_changed", 409)
        selected = next(
            item
            for item in catalog["commands"]
            if item["name"] == request.name and item["executable"]
        )
        if request.arguments and not selected["accepts_arguments"]:
            raise AssistantError("native_command_arguments_invalid", 422)
        async with self.store.transaction() as session:
            await self.store.authorize(session, context.owner_id, context.session_key)
            conversation = await self.store.conversation(
                session, context.owner_id, context.conversation_id, lock=True
            )
            message = await session.get(AssistantMessage, context.message_id)
            if (
                message is None
                or message.conversation_id != conversation.id
                or message.attempt_id != context.attempt_id
                or message.stop_requested
                or conversation.active_message_id != message.id
                or conversation.state not in {"starting", "running"}
            ):
                raise AssistantError("assistant_tool_authority_revoked", 403)
            prior = (
                await session.exec(
                    select(AssistantNativeAction).where(
                        AssistantNativeAction.conversation_id == conversation.id,
                        AssistantNativeAction.operation_key == request.operation_key,
                    )
                )
            ).first()
            if prior is not None:
                if prior.digest != request.digest():
                    raise AssistantError("assistant_action_conflict", 409)
                return prior.public(session_key=context.session_key)
            if conversation.run_id != catalog.get("run_id") or not catalog.get(
                "thread_id"
            ):
                raise AssistantError("assistant_native_identity_mismatch", 409)
            row = AssistantNativeAction(
                owner_id=context.owner_id,
                conversation_id=conversation.id,
                message_id=message.id,
                session_key=context.session_key,
                operation_key=request.operation_key,
                digest=request.digest(),
                request=request.model_dump(mode="json"),
                run_id=conversation.run_id,
                thread_id=catalog["thread_id"],
                expires_at=time.time() + 900,
            )
            session.add(row)
            await session.flush()
            await self.runtime.authorize(context)
            return row.public(session_key=context.session_key)

    async def list(self, owner, conversation_id, *, session_key=None):
        """Read only this owner's bounded retained native proposal cards."""
        async with self.store.sessions() as session:
            await self.store.conversation(session, owner, conversation_id)
            rows = (
                await session.exec(
                    select(AssistantNativeAction)
                    .where(
                        AssistantNativeAction.owner_id == owner,
                        AssistantNativeAction.conversation_id == conversation_id,
                    )
                    .order_by(AssistantNativeAction.created_at.desc())
                    .limit(50)
                )
            ).all()
            return [row.public(session_key=session_key) for row in reversed(rows)]

    async def read(self, owner, conversation_id, identifier, *, session_key=None):
        """Return one exact owner/conversation receipt without native dispatch authority."""
        async with self.store.sessions() as session:
            await self.store.conversation(session, owner, conversation_id)
            row = await session.get(AssistantNativeAction, identifier)
            if (
                row is None
                or row.owner_id != owner
                or row.conversation_id != conversation_id
            ):
                raise AssistantError("assistant_action_not_found", 404)
            return row.public(session_key=session_key)

    async def decide(self, owner, key, conversation_id, identifier, decision):
        """Commit approval and the command-message reservation atomically, or reject."""
        await self.runtime.check_session(owner, key)
        catalog = (
            await self.runtime.native_catalog(owner, conversation_id)
            if decision.decision == "approve"
            else {}
        )
        reserved = None
        async with self.store.transaction() as session:
            await self.store.authorize(session, owner, key)
            conversation = await self.store.conversation(
                session, owner, conversation_id, lock=True
            )
            row = await session.get(
                AssistantNativeAction, identifier, with_for_update=True
            )
            if (
                row is None
                or row.owner_id != owner
                or row.conversation_id != conversation_id
            ):
                raise AssistantError("assistant_action_not_found", 404)
            if row.session_key != key or row.digest != decision.digest:
                raise AssistantError("assistant_tool_authority_revoked", 403)
            if row.state != "pending":
                return row.public(session_key=key), None
            if row.expires_at <= time.time():
                row.state = "expired"
            elif decision.decision == "reject":
                row.state = "rejected"
            else:
                if conversation.active_message_id is not None:
                    raise AssistantError("assistant_turn_active", 409)
                request = NativeCommandRequest.model_validate(row.request)
                if (
                    conversation.run_id != row.run_id
                    or conversation.thread_id != row.thread_id
                    or catalog.get("run_id") != row.run_id
                    or catalog.get("thread_id") != row.thread_id
                    or catalog.get("revision") != request.catalog_revision
                ):
                    row.state = "stale"
                else:
                    selected = next(
                        (
                            item
                            for item in catalog.get("commands", [])
                            if item["name"] == request.name and item["executable"]
                        ),
                        None,
                    )
                    if selected is None or (
                        request.arguments and not selected["accepts_arguments"]
                    ):
                        raise AssistantError("native_command_not_available", 409)
                    reserved, created = await self.store.reserve_message(
                        session,
                        conversation,
                        MessageRequest(client_message_id=row.id, text=request.text()),
                        native_action_id=row.id,
                    )
                    if not created:
                        raise AssistantError("assistant_action_conflict", 409)
                    row.result_message_id = UUID(reserved["id"])
                    row.state = "executing"
            session.add(row)
            await session.flush()
            result = row.public(session_key=key)
        return result, reserved
