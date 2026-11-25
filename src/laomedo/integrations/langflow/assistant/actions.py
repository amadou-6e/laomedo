"""Durable model proposals and human-only graph effect admission."""

import time
from datetime import datetime, timezone
from copy import deepcopy
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.graph import GraphEditor
from laomedo.integrations.langflow.assistant.models import (
    AssistantGraphAction,
    AssistantGraphPermission,
    GraphActionRequest,
)
from laomedo.integrations.langflow.assistant.workflows import WorkflowDrafts


class WorkflowActions:
    """Separate proposing a graph action from authorizing and executing its exact effects."""

    def __init__(self, store, catalog, authorize, *, configuration=None):
        """Compose existing database/catalog ownership; retain no provider credentials."""
        self.store, self.catalog, self.authorize = store, catalog, authorize
        self.workflows = WorkflowDrafts(store, catalog, authorize)
        self.configuration = configuration

    async def flow(self, session, owner, identifier):
        """Read and lock only an existing graph owned by this authenticated app user."""
        from langflow.services.database.models.flow.model import Flow
        from langflow.services.database.models.flow.guards import lock_flow_for_update

        row = (
            await session.exec(
                select(Flow)
                .where(Flow.id == identifier, Flow.user_id == owner)
                .with_for_update()
            )
        ).first()
        if row is None:
            raise AssistantError("assistant_workflow_not_found", 404)
        await lock_flow_for_update(session, row)
        return row

    def editable(self, flow):
        """Preserve existing locked, published and filesystem-managed edit refusals."""
        if (
            flow.locked
            or flow.webhook
            or flow.mcp_enabled
            or flow.a2a_enabled
            or flow.fs_path
            or str(flow.access_type) not in {"PRIVATE", "AccessTypeEnum.PRIVATE"}
        ):
            raise AssistantError("assistant_draft_not_editable", 403)

    def run_data(self, data, request):
        """Apply only digest-bound typed runtime inputs to a private snapshot, never persisted rows."""
        result = deepcopy(data)
        nodes = {node["id"]: node for node in result.get("nodes", [])}
        seen = set()
        for value in request.node_inputs:
            key = value.node_id, value.field
            if key in seen or value.node_id not in nodes:
                raise AssistantError("assistant_input_invalid", 422)
            seen.add(key)
            node = nodes[value.node_id]
            identity = GraphEditor(self.catalog).identity(node)
            self.catalog.update_saved_fields(node, identity, {value.field: value.value})
        if (
            request.output_component is not None
            and request.output_component not in nodes
        ):
            raise AssistantError("assistant_input_invalid", 422)
        return result

    async def propose(self, context, request):
        """Record a bounded exact-revision proposal; never write the target or run it."""
        await self.authorize(context)
        if self.configuration is not None and request.kind == "edit":
            await self.configuration.prepare(
                context,
                self.catalog,
                [*request.changes.add_nodes, *request.changes.updates],
            )
        async with self.store.transaction() as session:
            await self.workflows.require_active(session, context)
            prior = (
                await session.exec(
                    select(AssistantGraphAction).where(
                        AssistantGraphAction.conversation_id == context.conversation_id,
                        AssistantGraphAction.operation_key == request.operation_key,
                    )
                )
            ).first()
            if prior:
                if prior.digest != request.digest():
                    raise AssistantError("assistant_action_conflict")
                return prior.public()
            flow = await self.flow(session, context.owner_id, request.workflow_id)
            if self.workflows.revision(flow) != request.expected_revision:
                raise AssistantError("assistant_source_revision_changed")
            if request.kind == "edit":
                self.editable(flow)
                _, preview = GraphEditor(self.catalog).apply(flow.data, request.changes)
                preview.append(
                    "Reload open editor tabs before saving; unsaved editor work may overwrite this saved change."
                )
            else:
                self.run_data(flow.data, request)
                preview = [
                    "Input: " + request.input_value,
                    "Input type: " + request.input_type,
                    "Output type: " + request.output_type,
                    "Node inputs: "
                    + request.model_dump_json(
                        include={"node_inputs", "output_component"}
                    ),
                    "Runs as your app user with your configured credentials/global variables.",
                    "May consume model quota and perform configured external actions. Chat Stop does not cancel graph runs.",
                ]
            if len(str(preview).encode()) > 65536:
                raise AssistantError("assistant_graph_too_large", 422)
            row = AssistantGraphAction(
                owner_id=context.owner_id,
                session_key=context.session_key,
                conversation_id=context.conversation_id,
                message_id=context.message_id,
                attempt_id=context.attempt_id,
                operation_key=request.operation_key,
                workflow_id=flow.id,
                name=flow.name[:120],
                kind=request.kind,
                digest=request.digest(),
                request=request.model_dump(mode="json"),
                preview=preview,
                revision=request.expected_revision,
                expires_at=time.time() + 900,
            )
            session.add(row)
            await session.flush()
            await self.authorize(context)
            return row.public()

    async def read(self, owner, conversation, identifier, *, session_key=None):
        """Project one conversation-owned action without exposing host/session/request internals."""
        async with self.store.sessions() as session:
            await self.store.conversation(session, owner, conversation)
            row = await session.get(AssistantGraphAction, identifier)
            if (
                row is None
                or row.owner_id != owner
                or row.conversation_id != conversation
            ):
                raise AssistantError("assistant_workflow_not_found", 404)
            return row.public(session_key=session_key)

    async def list(self, owner, conversation, *, session_key=None):
        """Return bounded retained proposal and outcome cards without native inference."""
        async with self.store.sessions() as session:
            await self.store.conversation(session, owner, conversation)
            rows = (
                await session.exec(
                    select(AssistantGraphAction)
                    .where(
                        AssistantGraphAction.owner_id == owner,
                        AssistantGraphAction.conversation_id == conversation,
                    )
                    .order_by(AssistantGraphAction.created_at.desc())
                    .limit(50)
                )
            ).all()
            return [row.public(session_key=session_key) for row in reversed(rows)]

    async def decide(
        self, owner, key, conversation, identifier, decision, *, context=None
    ):
        """Human-only exact-digest decision; edit atomically or return a once-claimed run snapshot."""
        from langflow.services.database.models.user.model import User
        from langflow.services.database.models.flow.model import FlowRead
        from langflow.services.database.models.flow.guards import (
            ensure_flow_update_allowed,
        )
        from langflow.services.authorization import FlowAction, ensure_flow_permission
        from langflow.api.v1.flows import _validate_catalog_policy_for_write
        from langflow.services.deps import get_catalog_policy_service

        snapshot = actor = None
        async with self.store.transaction() as session:
            await self.store.authorize(session, owner, key)
            await self.store.conversation(session, owner, conversation, lock=True)
            actor = await session.get(User, owner)
            row = await session.get(
                AssistantGraphAction,
                identifier,
                with_for_update=True,
            )
            if (
                row is None
                or row.owner_id != owner
                or row.conversation_id != conversation
            ):
                raise AssistantError("assistant_workflow_not_found", 404)
            if actor is None or not actor.is_active or row.session_key != key:
                raise AssistantError("assistant_session_locked", 403)
            if row.digest != decision.digest:
                raise AssistantError("assistant_action_conflict")
            request = GraphActionRequest.model_validate(row.request)
            permission = (
                await session.exec(
                    select(AssistantGraphPermission).where(
                        AssistantGraphPermission.owner_id == owner,
                        AssistantGraphPermission.conversation_id == conversation,
                        AssistantGraphPermission.session_key == key,
                        AssistantGraphPermission.category == request.category,
                    )
                )
            ).first()
            if context is not None:
                await self.authorize(context)
                await self.workflows.require_active(session, context)
                if permission is None:
                    return row.public(session_key=key), None, None
            if row.state != "pending":
                return row.public(), None, None
            if row.expires_at <= time.time():
                row.state = "expired"
            elif decision.decision == "reject":
                row.state = "rejected"
            else:
                flow = await self.flow(session, owner, row.workflow_id)
                if self.workflows.revision(flow) != row.revision:
                    row.state = "stale"
                    row.error_code = "assistant_source_revision_changed"
                else:
                    if self.configuration is not None:
                        from laomedo.integrations.langflow.assistant.models import (
                            AuthoringContext,
                        )

                        binding_context = AuthoringContext(
                            owner_id=owner,
                            conversation_id=conversation,
                            message_id=row.message_id,
                            attempt_id=row.attempt_id,
                            session_key=key,
                        )
                        if row.kind == "run":
                            await self.configuration.check_graph(
                                binding_context, self.catalog, flow.data, active=False
                            )
                        if row.kind == "edit":
                            await self.configuration.prepare(
                                binding_context,
                                self.catalog,
                                [*request.changes.add_nodes, *request.changes.updates],
                                active=False,
                            )
                    await ensure_flow_permission(
                        actor,
                        FlowAction.WRITE if row.kind == "edit" else FlowAction.EXECUTE,
                        flow_id=flow.id,
                        flow_user_id=flow.user_id,
                        workspace_id=flow.workspace_id,
                        folder_id=flow.folder_id,
                    )
                    request = GraphActionRequest.model_validate(row.request)
                    if row.kind == "edit":
                        self.editable(flow)
                        data, _ = GraphEditor(self.catalog).apply(
                            flow.data, request.changes
                        )
                        _validate_catalog_policy_for_write(
                            data, snapshot=get_catalog_policy_service().snapshot
                        )
                        name = (
                            request.changes.name
                            if request.changes.name is not None
                            else flow.name
                        )
                        ensure_flow_update_allowed(flow, {"name": name, "data": data})
                        try:
                            async with session.begin_nested():
                                flow.name, flow.data = name, data
                                flow.updated_at = datetime.now(timezone.utc)
                                session.add(flow)
                                await session.flush()
                                await session.refresh(flow)
                                result_revision = self.workflows.revision(flow)
                        except IntegrityError:
                            row.state = "failed"
                            row.error_code = "assistant_graph_name_conflict"
                        else:
                            row.state, row.result_revision = (
                                "succeeded",
                                result_revision,
                            )
                    else:
                        row.state, row.run_id = "executing", uuid4()
                        snapshot = FlowRead.model_validate(
                            flow, from_attributes=True
                        ).model_copy(deep=True)
            if (
                decision.decision == "always_approve"
                and context is None
                and row.state in {"succeeded", "executing"}
                and permission is None
            ):
                session.add(
                    AssistantGraphPermission(
                        owner_id=owner,
                        conversation_id=conversation,
                        session_key=key,
                        category=request.category,
                        action_id=row.id,
                    )
                )
            session.add(row)
            await session.flush()
            result = row.public()
        return result, snapshot, actor

    async def permissions(self, owner, key, conversation):
        """List only current-session human grants for the owning conversation."""
        async with self.store.sessions() as session:
            await self.store.authorize(session, owner, key)
            await self.store.conversation(session, owner, conversation)
            rows = (
                await session.exec(
                    select(AssistantGraphPermission).where(
                        AssistantGraphPermission.owner_id == owner,
                        AssistantGraphPermission.conversation_id == conversation,
                        AssistantGraphPermission.session_key == key,
                    )
                )
            ).all()
            return sorted(row.category for row in rows)

    async def revoke_permission(self, owner, key, conversation, category):
        """Serialize human revocation with decisions; already admitted effects continue."""
        if category not in {"rename", "edit", "run"}:
            raise AssistantError("assistant_input_invalid", 422)
        async with self.store.transaction() as session:
            await self.store.authorize(session, owner, key)
            await self.store.conversation(session, owner, conversation, lock=True)
            rows = (
                await session.exec(
                    select(AssistantGraphPermission).where(
                        AssistantGraphPermission.owner_id == owner,
                        AssistantGraphPermission.conversation_id == conversation,
                        AssistantGraphPermission.session_key == key,
                        AssistantGraphPermission.category == category,
                    )
                )
            ).all()
            for row in rows:
                await session.delete(row)
        return {"category": category, "state": "revoked"}

    async def finish(self, identifier, state, error=None):
        """Persist a safe outcome without overwriting an already settled result."""
        async with self.store.transaction() as session:
            row = await session.get(
                AssistantGraphAction,
                identifier,
                with_for_update=True,
            )
            if row and row.state in {"executing", "unknown"}:
                row.state, row.error_code = state, error
                session.add(row)

    async def execute(self, result, snapshot, actor, check_session, *, entered=None):
        """Invoke the existing caller-aware execution owner once using the approved snapshot."""
        if entered is not None:
            entered.set()
        from langflow.api.v1.endpoints import simple_run_flow
        from langflow.api.v1.schemas import SimplifiedAPIRequest
        import asyncio

        identifier = UUID(result["id"])
        dispatched = False
        returned = False
        try:
            async with self.store.sessions() as session:
                row = await session.get(AssistantGraphAction, identifier)
                request = GraphActionRequest.model_validate(row.request)
                key = row.session_key
            await check_session(actor.id, key)
            from langflow.services.authorization import (
                FlowAction,
                ensure_flow_permission,
            )
            from langflow.services.database.models.user.model import User

            async with self.store.sessions() as session:
                actor = await session.get(User, actor.id)
                if actor is None or not actor.is_active:
                    raise AssistantError("assistant_session_locked", 403)
            await ensure_flow_permission(
                actor,
                FlowAction.EXECUTE,
                flow_id=snapshot.id,
                flow_user_id=snapshot.user_id,
                workspace_id=snapshot.workspace_id,
                folder_id=snapshot.folder_id,
            )
            # Explicit editor-side context selects the cold path, retaining the
            # approved snapshot; native graph policies/global resolution still run.
            input_request = SimplifiedAPIRequest(
                input_value=request.input_value,
                input_type=request.input_type,
                output_type=request.output_type,
                output_component=request.output_component or "",
                session_id="assistant-action-" + str(identifier),
            )
            snapshot = snapshot.model_copy(
                update={"data": self.run_data(snapshot.data, request)}, deep=True
            )
            if self.configuration is not None:
                from laomedo.integrations.langflow.assistant.models import (
                    AuthoringContext,
                )

                context = AuthoringContext(
                    owner_id=row.owner_id,
                    conversation_id=row.conversation_id,
                    message_id=row.message_id,
                    attempt_id=row.attempt_id,
                    session_key=key,
                )
                await self.configuration.check_graph(
                    context, self.catalog, snapshot.data, active=False
                )
            dispatched = True
            response = await simple_run_flow(
                snapshot,
                input_request,
                api_key_user=actor,
                run_id=result["run_id"],
                context={},
                http_request=None,
                expose_error_details=False,
            )
            returned = True
            from laomedo.integrations.langflow.assistant.evidence import (
                WorkflowRunEvidence,
            )

            captured = await WorkflowRunEvidence(self).retain(
                result, response, data=snapshot.data
            )
            await self.finish(
                identifier,
                "succeeded",
                None if captured else "assistant_output_capture_failed",
            )
        except asyncio.CancelledError:
            await asyncio.shield(
                self.finish(
                    identifier,
                    (
                        "succeeded"
                        if returned
                        else "unknown" if dispatched else "not_dispatched"
                    ),
                    (
                        "assistant_output_capture_failed"
                        if returned
                        else (
                            "assistant_action_outcome_unknown"
                            if dispatched
                            else "assistant_action_not_dispatched"
                        )
                    ),
                )
            )
            raise
        except Exception:
            if returned:
                await self.finish(
                    identifier, "succeeded", "assistant_output_capture_failed"
                )
            elif not dispatched:
                await self.finish(
                    identifier, "not_dispatched", "assistant_action_not_dispatched"
                )
            else:
                await self.reconcile(identifier)

    async def reconcile(self, identifier=None):
        """Observe exact owned workflow jobs after restart; never execute a stored proposal."""
        from langflow.services.deps import get_job_service

        async with self.store.sessions() as session:
            rows = (
                await session.exec(
                    select(AssistantGraphAction).where(
                        AssistantGraphAction.state.in_(["executing", "unknown"]),
                        *(
                            [AssistantGraphAction.id == identifier]
                            if identifier
                            else []
                        ),
                    )
                )
            ).all()
        for row in rows:
            state = "unknown"
            try:
                job = await get_job_service().get_job_by_job_id(
                    row.run_id, user_id=row.owner_id
                )
                if (
                    job
                    and job.user_id == row.owner_id
                    and job.flow_id == row.workflow_id
                ):
                    value = str(getattr(job.status, "value", job.status))
                    if value == "completed":
                        state = "succeeded"
                    elif value == "cancelled":
                        state = "cancelled"
                    elif value in {"failed", "timed_out"}:
                        state = "failed"
            except Exception:
                pass
            await self.finish(
                row.id,
                state,
                (
                    "assistant_action_outcome_unknown"
                    if state == "unknown"
                    else "assistant_graph_run_failed" if state == "failed" else None
                ),
            )
