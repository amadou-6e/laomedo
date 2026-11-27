"""Narrow authoring operations using ordinary Langflow Flow rows and atomic receipts."""

from datetime import datetime, timezone
import hashlib
import json
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.models import (
    AssistantDraftReceipt,
    AssistantMessage,
)


class WorkflowDrafts:
    """Project owner-visible workflows and conditionally save this conversation's drafts."""

    def __init__(self, store, catalog, authorize, *, configuration=None):
        """Use the app database/catalog and an explicit host session-authority check."""
        self.store, self.catalog, self.authorize = store, catalog, authorize
        self.configuration = configuration

    def revision(self, flow):
        """Digest the complete persisted Flow, not a lossy timestamp-only projection."""
        return (
            "sha256:"
            + hashlib.sha256(
                json.dumps(
                    flow.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
        )

    async def require_active(self, session, context):
        """Fence tool effects against the current owner, session and exact active attempt."""
        await self.authorize(context)
        await self.store.authorize(session, context.owner_id, context.session_key)
        conversation = await self.store.conversation(
            session, context.owner_id, context.conversation_id, lock=True
        )
        message = await session.get(AssistantMessage, context.message_id)
        if (
            message is None
            or message.conversation_id != conversation.id
            or message.attempt_id != context.attempt_id
            or conversation.active_message_id != message.id
            or conversation.state not in {"starting", "running"}
        ):
            raise AssistantError("assistant_tool_authority_revoked", 403)
        return conversation

    async def list(self, context, query="", cursor=0):
        """Read bounded summaries without data, code, account settings or other owners."""
        from langflow.services.database.models.flow.model import Flow

        if len(query) > 200 or cursor < 0 or cursor > 10000:
            raise AssistantError("assistant_input_invalid", 400)
        await self.authorize(context)
        async with self.store.sessions() as session:
            await self.store.conversation(
                session, context.owner_id, context.conversation_id
            )
            statement = select(Flow).where(
                Flow.user_id == context.owner_id, Flow.is_component.is_not(True)
            )
            if query:
                statement = statement.where(Flow.name.contains(query, autoescape=True))
            rows = (
                await session.exec(
                    statement.order_by(Flow.name, Flow.id).offset(cursor).limit(21)
                )
            ).all()
            result = {
                "workflows": [
                    {
                        "workflow_id": str(row.id),
                        "name": row.name[:120],
                        "revision": self.revision(row),
                    }
                    for row in rows[:20]
                ],
                "next_cursor": cursor + 20 if len(rows) > 20 else None,
            }
        await self.authorize(context)
        return result

    async def get(self, context, workflow_id):
        """Return an explicit non-secret metadata projection, never raw saved component bytes."""
        from langflow.services.database.models.flow.model import Flow

        await self.authorize(context)
        async with self.store.sessions() as session:
            await self.store.conversation(
                session, context.owner_id, context.conversation_id
            )
            flow = (
                await session.exec(
                    select(Flow).where(
                        Flow.id == workflow_id, Flow.user_id == context.owner_id
                    )
                )
            ).first()
            if flow is None:
                raise AssistantError("assistant_workflow_not_found", 404)
            result = {
                "workflow_id": str(flow.id),
                "name": flow.name[:120],
                "revision": self.revision(flow),
                "spec": self.catalog.project(flow.data),
            }
            if self.configuration is not None:
                result["spec"] = await self.configuration.project(
                    context, self.catalog, flow.data
                )
        await self.authorize(context)
        return result

    async def save(self, context, request):
        """Commit a complete Flow and authoritative receipt atomically; edits require exact revision."""
        from langflow.api.v1.flows_helpers import _validate_and_assign_folder
        from langflow.services.database.models.flow.guards import (
            lock_flow_for_update,
            ensure_flow_update_allowed,
        )
        from langflow.services.database.models.flow.model import Flow

        digest = hashlib.sha256(
            json.dumps(
                request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        try:
            async with self.store.transaction() as session:
                await self.require_active(session, context)
                prior = (
                    await session.exec(
                        select(AssistantDraftReceipt).where(
                            AssistantDraftReceipt.conversation_id
                            == context.conversation_id,
                            AssistantDraftReceipt.draft_key == request.draft_key,
                        )
                    )
                ).first()
                if prior:
                    if prior.digest != digest:
                        raise AssistantError("assistant_draft_key_conflict")
                    return prior.model_dump(mode="json", exclude={"digest", "owner_id"})
                data, diagnostics = self.catalog.compile(request.spec)
                # The same transaction/row locks cover revision observations and
                # writes, including editor writers using Langflow's Flow guard.
                for source in sorted(
                    request.sources, key=lambda value: str(value.workflow_id)
                ):
                    row = (
                        await session.exec(
                            select(Flow)
                            .where(
                                Flow.id == source.workflow_id,
                                Flow.user_id == context.owner_id,
                            )
                            .with_for_update()
                        )
                    ).first()
                    if row is None or self.revision(row) != source.revision:
                        raise AssistantError("assistant_source_revision_changed")
                    projected = self.catalog.project(row.data)
                    for node in projected["nodes"]:
                        for name in node.get("unresolved_fields", []):
                            diagnostics.append(
                                "Source "
                                + str(source.workflow_id)
                                + " "
                                + node["key"]
                                + "."
                                + name
                                + ": setting was not copied"
                            )
                if (
                    any(not text.startswith("warning: ") for text in diagnostics)
                    and not request.spec.allow_incomplete
                ):
                    raise AssistantError("assistant_draft_incomplete", 422)
                if request.draft_id:
                    owned = (
                        await session.exec(
                            select(AssistantDraftReceipt).where(
                                AssistantDraftReceipt.owner_id == context.owner_id,
                                AssistantDraftReceipt.conversation_id
                                == context.conversation_id,
                                AssistantDraftReceipt.workflow_id == request.draft_id,
                            )
                        )
                    ).first()
                    if owned is None:
                        raise AssistantError("assistant_draft_not_owned", 403)
                    flow = (
                        await session.exec(
                            select(Flow)
                            .where(
                                Flow.id == request.draft_id,
                                Flow.user_id == context.owner_id,
                            )
                            .with_for_update()
                        )
                    ).first()
                    if flow is None:
                        raise AssistantError("assistant_workflow_not_found", 404)
                    await lock_flow_for_update(session, flow)
                    if self.revision(flow) != request.expected_revision:
                        raise AssistantError("assistant_draft_revision_changed")
                    if (
                        flow.locked
                        or flow.webhook
                        or flow.mcp_enabled
                        or flow.a2a_enabled
                        or flow.fs_path
                        or str(flow.access_type)
                        not in {"PRIVATE", "AccessTypeEnum.PRIVATE"}
                    ):
                        raise AssistantError("assistant_draft_not_editable", 403)
                    ensure_flow_update_allowed(
                        flow, {"name": request.name, "data": data}
                    )
                    flow.name, flow.data = request.name, data
                    flow.updated_at = datetime.now(timezone.utc)
                else:
                    flow = Flow(
                        name=request.name,
                        data=data,
                        user_id=context.owner_id,
                        description="Assistant draft. Structural checks only; execution has not been validated.",
                        webhook=False,
                        mcp_enabled=False,
                        a2a_enabled=False,
                    )
                    await _validate_and_assign_folder(session, flow, context.owner_id)
                await self.authorize(context)
                session.add(flow)
                await session.flush()
                await session.refresh(flow)
                receipt = AssistantDraftReceipt(
                    owner_id=context.owner_id,
                    conversation_id=context.conversation_id,
                    message_id=context.message_id,
                    attempt_id=context.attempt_id,
                    draft_key=request.draft_key,
                    digest=digest,
                    workflow_id=flow.id,
                    name=flow.name,
                    revision=self.revision(flow),
                    diagnostics=diagnostics,
                )
                session.add(receipt)
                await session.flush()
                result = receipt.model_dump(mode="json", exclude={"digest", "owner_id"})
                await self.authorize(context)
            return result
        except SQLAlchemyError:
            # Commit may have reached the database. The caller must look up its
            # operation key, not assume failure and create a new operation.
            raise AssistantError("assistant_save_outcome_unknown", 503) from None
