"""Current approval authority, exact-revision editing and non-replayed run admission."""

import asyncio
from copy import deepcopy
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from langflow.services.database.models.flow.model import Flow
from langflow.services.database.models.user.model import User
from langflow.services.database.models.folder.model import Folder
from langflow.services.database.models.folder.constants import DEFAULT_FOLDER_NAME
from laomedo.integrations.langflow.assistant.actions import WorkflowActions
from laomedo.integrations.langflow.assistant.catalog import ComponentCatalog
from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.graph import GraphEditor
from laomedo.integrations.langflow.assistant.models import (
    AuthoringContext,
    ConversationRequest,
    MessageRequest,
    DraftGraph,
    DraftNode,
    GraphChanges,
    GraphActionRequest,
    GraphActionDecision,
    AssistantGraphAction,
)
from laomedo.integrations.langflow.assistant.persistence import AssistantStore


class GraphActionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = create_async_engine(
            "sqlite+aiosqlite:///" + (Path(self.directory.name) / "app.db").as_posix()
        )
        async with self.engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)
        self.store = AssistantStore(self.engine)
        self.owner = uuid4()
        async with self.store.transaction() as session:
            session.add(
                User(
                    id=self.owner, username="owner", password="fixture", is_active=True
                )
            )
            session.add(Folder(name=DEFAULT_FOLDER_NAME, user_id=self.owner))
        await self.store.admit_session("fixture", self.owner, time.time() + 2000)
        conversation = await self.store.create(
            self.owner,
            ConversationRequest(
                connection_id=uuid4(),
                connection_generation=1,
                model="fixture",
                effort="low",
            ),
            session_key="fixture",
        )
        self.conversation = UUID(conversation["id"])
        message, _ = await self.store.reserve(
            self.owner,
            self.conversation,
            MessageRequest(client_message_id=uuid4(), text="Edit this graph"),
            session_key="fixture",
        )
        self.context = AuthoringContext(
            owner_id=self.owner,
            conversation_id=self.conversation,
            message_id=UUID(message["id"]),
            attempt_id=UUID(message["attempt_id"]),
            session_key="fixture",
        )
        self.catalog = ComponentCatalog(
            {
                "test": {
                    "Text": {
                        "template": {
                            "code": {"value": "TRUSTED_CODE"},
                            "text": {"type": "str", "value": "old"},
                            "api_key": {"type": "str", "password": True, "value": None},
                        },
                        "outputs": [{"name": "text", "types": ["Message"]}],
                    }
                }
            }
        )
        data, _ = self.catalog.compile(
            DraftGraph(
                nodes=[
                    DraftNode(key="one", component_type="test/Text"),
                    DraftNode(key="two", component_type="test/Text"),
                ],
                allow_incomplete=True,
            )
        )
        data["nodes"][0]["data"]["node"]["template"]["api_key"][
            "value"
        ] = "PRIVATE_CANARY"
        self.original = deepcopy(data)
        async with self.store.transaction() as session:
            row = Flow(name="Existing graph", data=data, user_id=self.owner)
            session.add(row)
            await session.flush()
            await session.refresh(row)
            self.flow_id = row.id
        self.actions = WorkflowActions(self.store, self.catalog, AsyncMock())
        async with self.store.transaction() as session:
            row = await self.actions.flow(session, self.owner, self.flow_id)
            self.revision = self.actions.workflows.revision(row)
        self.request = GraphActionRequest(
            operation_key="edit-one",
            kind="edit",
            workflow_id=self.flow_id,
            expected_revision=self.revision,
            changes=GraphChanges.model_validate(
                {"updates": [{"node_id": "Text-one", "fields": {"text": "new"}}]}
            ),
        )
        self.permissions = patch(
            "langflow.services.authorization.ensure_flow_permission", new=AsyncMock()
        )
        self.policy = patch("langflow.api.v1.flows._validate_catalog_policy_for_write")
        self.job_service = patch(
            "langflow.services.deps.get_job_service", return_value=AsyncMock()
        )
        self.job_service.start().return_value.get_job_by_job_id.return_value = None
        self.permissions.start()
        self.policy.start()

    async def asyncTearDown(self):
        self.permissions.stop()
        self.policy.stop()
        self.job_service.stop()
        await self.engine.dispose()
        self.directory.cleanup()

    async def test_actual_run_output_projection_is_durable_and_conversation_scoped(
        self,
    ):
        from lfx.graph.schema import RunOutputs, ResultData
        from lfx.schema.message import Message
        from langflow.api.v1.schemas import RunResponse
        from laomedo.integrations.langflow.assistant.evidence import WorkflowRunEvidence

        request = GraphActionRequest(
            operation_key="output-run",
            kind="run",
            workflow_id=self.flow_id,
            expected_revision=self.revision,
        )
        proposal = await self.actions.propose(self.context, request)
        result, _, _ = await self.decide(proposal)
        evidence = WorkflowRunEvidence(self.actions)
        response = RunResponse(
            outputs=[
                RunOutputs(
                    outputs=[
                        ResultData(
                            component_id="Text-one",
                            results={"answer": Message(text="actual output")},
                            logs={"private": "LOG_CANARY"},
                            artifacts={"private": "ARTIFACT_CANARY"},
                        )
                    ]
                )
            ],
            session_id="test",
        )
        await evidence.retain(result, response)
        await self.actions.finish(UUID(result["id"]), "succeeded")
        observed = await evidence.read(self.context, UUID(result["id"]))
        self.assertEqual(observed["outputs"][0]["value"], "actual output")
        self.assertTrue(observed["output_available"])
        self.assertNotIn("CANARY", str(observed))
        self.assertEqual(observed["revision"], self.revision)
        other = self.context.model_copy(update={"conversation_id": uuid4()})
        with self.assertRaises(AssistantError):
            await evidence.read(other, UUID(result["id"]))
        await self.store.revoke("fixture")
        with self.assertRaises(AssistantError):
            await evidence.read(self.context, UUID(result["id"]))

    async def test_absent_output_is_not_invented_and_sensitive_structures_are_omitted(
        self,
    ):
        from laomedo.integrations.langflow.assistant.evidence import WorkflowRunEvidence

        projected = WorkflowRunEvidence.safe_value(
            {
                "text": "useful",
                "api_key": "KEY_CANARY",
                "nested": {"authorization": "PRIVATE", "value": 3},
            }
        )
        self.assertEqual(projected, {"text": "useful", "nested": {"value": 3}})
        with self.assertRaises(ValueError):
            WorkflowRunEvidence.safe_value(object())
        with self.assertRaises(ValueError):
            WorkflowRunEvidence.safe_value("x" * 65537)

    async def test_pending_run_has_no_execution_identity_or_invented_output(self):
        from laomedo.integrations.langflow.assistant.evidence import WorkflowRunEvidence

        request = GraphActionRequest(
            operation_key="pending-output",
            kind="run",
            workflow_id=self.flow_id,
            expected_revision=self.revision,
        )
        proposal = await self.actions.propose(self.context, request)
        observed = await WorkflowRunEvidence(self.actions).read(
            self.context, UUID(proposal["id"])
        )
        self.assertEqual(observed["state"], "pending")
        self.assertIsNone(observed["run_id"])
        self.assertFalse(observed["output_available"])
        self.assertFalse(observed["node_status_available"])
        self.assertEqual(observed["outputs"], [])

    async def test_output_capture_failure_preserves_success_without_replaying_the_run(
        self,
    ):
        request = GraphActionRequest(
            operation_key="capture-failure",
            kind="run",
            workflow_id=self.flow_id,
            expected_revision=self.revision,
        )
        proposal = await self.actions.propose(self.context, request)
        result, snapshot, actor = await self.decide(proposal)
        with (
            patch(
                "langflow.api.v1.endpoints.simple_run_flow", new=AsyncMock()
            ) as execute,
            patch(
                "laomedo.integrations.langflow.assistant.evidence.WorkflowRunEvidence.retain",
                new=AsyncMock(side_effect=RuntimeError("private database diagnostic")),
            ),
        ):
            await self.actions.execute(result, snapshot, actor, AsyncMock())
            execute.assert_awaited_once()
        observed = await self.actions.read(
            self.owner, self.conversation, UUID(result["id"])
        )
        self.assertEqual(observed["state"], "succeeded")
        self.assertEqual(observed["error_code"], "assistant_output_capture_failed")
        self.assertNotIn("private database diagnostic", str(observed))

    async def decide(self, proposal, decision="approve", key="fixture"):
        return await self.actions.decide(
            self.owner,
            key,
            self.conversation,
            UUID(proposal["id"]),
            GraphActionDecision(decision=decision, digest=proposal["digest"]),
        )

    async def test_category_comes_from_changes_and_summary_is_bound(self):
        rename = self.request.model_copy(
            update={
                "changes": GraphChanges(name="Renamed graph"),
                "summary": "Rename this workflow.",
            }
        )
        self.assertEqual(rename.category, "rename")
        self.assertEqual(self.request.category, "edit")
        mixed = rename.model_copy(
            update={
                "changes": GraphChanges(
                    name="Renamed graph", updates=self.request.changes.updates
                )
            }
        )
        self.assertEqual(mixed.category, "edit")
        self.assertNotEqual(
            rename.digest(),
            rename.model_copy(update={"summary": "Other text"}).digest(),
        )
        proposal = await self.actions.propose(self.context, rename)
        self.assertEqual(proposal["category"], "rename")
        self.assertEqual(proposal["new_name"], "Renamed graph")
        self.assertEqual(proposal["summary"], "Rename this workflow.")
        async with self.store.sessions() as session:
            flow = await session.get(Flow, self.flow_id)
            self.assertEqual(flow.name, "Existing graph")

    async def test_always_approve_is_category_conversation_and_session_scoped(self):
        proposal = await self.actions.propose(self.context, self.request)
        await self.decide(proposal, "always_approve")
        self.assertEqual(
            await self.actions.permissions(self.owner, "fixture", self.conversation),
            ["edit"],
        )
        async with self.store.transaction() as session:
            other = Flow(
                name="Second graph", data=deepcopy(self.original), user_id=self.owner
            )
            session.add(other)
            await session.flush()
            await session.refresh(other)
            identifier, revision = other.id, self.actions.workflows.revision(other)
        followup = self.request.model_copy(
            update={
                "operation_key": "other-graph",
                "workflow_id": identifier,
                "expected_revision": revision,
            }
        )
        pending = await self.actions.propose(self.context, followup)
        result, snapshot, _ = await self.actions.decide(
            self.owner,
            "fixture",
            self.conversation,
            UUID(pending["id"]),
            GraphActionDecision(decision="approve", digest=pending["digest"]),
            context=self.context,
        )
        self.assertEqual(result["state"], "succeeded")
        self.assertIsNone(snapshot)
        async with self.store.sessions() as session:
            other = await session.get(Flow, identifier)
            revision = self.actions.workflows.revision(other)
        rename = followup.model_copy(
            update={
                "operation_key": "rename-no-grant",
                "expected_revision": revision,
                "changes": GraphChanges(name="Not approved"),
            }
        )
        pending = await self.actions.propose(self.context, rename)
        result, _, _ = await self.actions.decide(
            self.owner,
            "fixture",
            self.conversation,
            UUID(pending["id"]),
            GraphActionDecision(decision="approve", digest=pending["digest"]),
            context=self.context,
        )
        self.assertEqual(result["state"], "pending")
        run = followup.model_copy(
            update={
                "operation_key": "run-no-grant",
                "expected_revision": revision,
                "kind": "run",
                "changes": None,
            }
        )
        pending = await self.actions.propose(self.context, run)
        result, snapshot, _ = await self.actions.decide(
            self.owner,
            "fixture",
            self.conversation,
            UUID(pending["id"]),
            GraphActionDecision(decision="approve", digest=pending["digest"]),
            context=self.context,
        )
        self.assertEqual(result["state"], "pending")
        self.assertIsNone(snapshot)
        await self.store.admit_session("other-session", self.owner, time.time() + 1000)
        self.assertEqual(
            await self.actions.permissions(
                self.owner, "other-session", self.conversation
            ),
            [],
        )
        separate = await self.store.create(
            self.owner,
            ConversationRequest(
                connection_id=uuid4(),
                connection_generation=1,
                model="fixture",
                effort="low",
            ),
            session_key="fixture",
        )
        self.assertEqual(
            await self.actions.permissions(self.owner, "fixture", UUID(separate["id"])),
            [],
        )
        await self.actions.revoke_permission(
            self.owner, "fixture", self.conversation, "edit"
        )
        self.assertEqual(
            await self.actions.permissions(self.owner, "fixture", self.conversation), []
        )
        following = followup.model_copy(
            update={"operation_key": "after-revoke", "expected_revision": revision}
        )
        pending = await self.actions.propose(self.context, following)
        result, _, _ = await self.actions.decide(
            self.owner,
            "fixture",
            self.conversation,
            UUID(pending["id"]),
            GraphActionDecision(decision="approve", digest=pending["digest"]),
            context=self.context,
        )
        self.assertEqual(result["state"], "pending")

    async def test_stale_and_expired_always_approval_never_grants_consent(self):
        for outcome in ("stale", "expired"):
            with self.subTest(outcome=outcome):
                async with self.store.sessions() as session:
                    flow = await session.get(Flow, self.flow_id)
                    revision = self.actions.workflows.revision(flow)
                request = self.request.model_copy(
                    update={
                        "operation_key": "grant-" + outcome,
                        "expected_revision": revision,
                    }
                )
                proposal = await self.actions.propose(self.context, request)
                async with self.store.transaction() as session:
                    if outcome == "expired":
                        row = await session.get(
                            AssistantGraphAction, UUID(proposal["id"])
                        )
                        row.expires_at = 0
                    else:
                        row = await session.get(Flow, self.flow_id)
                        row.name = "Changed externally"
                    session.add(row)
                result, snapshot, _ = await self.decide(proposal, "always_approve")
                self.assertEqual(result["state"], outcome)
                self.assertIsNone(snapshot)
                self.assertEqual(
                    await self.actions.permissions(
                        self.owner, "fixture", self.conversation
                    ),
                    [],
                )

    async def test_concurrent_always_run_claims_once_and_creates_one_grant(self):
        request = self.request.model_copy(
            update={"operation_key": "always-run", "kind": "run", "changes": None}
        )
        proposal = await self.actions.propose(self.context, request)
        results = await asyncio.gather(
            self.decide(proposal, "always_approve"),
            self.decide(proposal, "always_approve"),
        )
        self.assertEqual(sum(snapshot is not None for _, snapshot, _ in results), 1)
        self.assertEqual(results[0][0]["run_id"], results[1][0]["run_id"])
        self.assertEqual(
            await self.actions.permissions(self.owner, "fixture", self.conversation),
            ["run"],
        )

    async def test_auto_consent_refuses_other_session_and_preserves_pending_on_policy_error(
        self,
    ):
        proposal = await self.actions.propose(self.context, self.request)
        await self.decide(proposal, "always_approve")
        async with self.store.sessions() as session:
            flow = await session.get(Flow, self.flow_id)
            before = deepcopy(flow.data)
            revision = self.actions.workflows.revision(flow)
        request = self.request.model_copy(
            update={"operation_key": "auto-refusal", "expected_revision": revision}
        )
        proposal = await self.actions.propose(self.context, request)
        decision = GraphActionDecision(decision="approve", digest=proposal["digest"])
        await self.store.admit_session("other", self.owner, time.time() + 1000)
        with self.assertRaises(AssistantError):
            await self.actions.decide(
                self.owner,
                "other",
                self.conversation,
                UUID(proposal["id"]),
                decision,
                context=self.context.model_copy(update={"session_key": "other"}),
            )
        with patch(
            "langflow.services.authorization.ensure_flow_permission",
            new=AsyncMock(side_effect=RuntimeError("policy refusal")),
        ):
            with self.assertRaises(RuntimeError):
                await self.actions.decide(
                    self.owner,
                    "fixture",
                    self.conversation,
                    UUID(proposal["id"]),
                    decision,
                    context=self.context,
                )
        retained = await self.actions.read(
            self.owner, self.conversation, UUID(proposal["id"]), session_key="fixture"
        )
        self.assertEqual(retained["state"], "pending")
        self.assertTrue(retained["can_decide"])
        async with self.store.sessions() as session:
            flow = await session.get(Flow, self.flow_id)
            self.assertEqual(flow.data, before)

    async def test_proposal_is_inert_edit_commits_once_and_preserves_private_bytes(
        self,
    ):
        proposal = await self.actions.propose(self.context, self.request)
        self.assertEqual(
            proposal, await self.actions.propose(self.context, self.request)
        )
        self.assertNotIn("PRIVATE_CANARY", str(proposal))
        self.assertNotIn("TRUSTED_CODE", str(proposal))
        async with self.store.sessions() as session:
            self.assertEqual(
                (await session.get(Flow, self.flow_id)).data, self.original
            )
        result, snapshot, _ = await self.decide(proposal)
        self.assertEqual(result["state"], "succeeded")
        self.assertIsNone(snapshot)
        again, _, _ = await self.decide(proposal)
        self.assertEqual(again, result)
        async with self.store.sessions() as session:
            changed = (await session.get(Flow, self.flow_id)).data
        expected = deepcopy(self.original)
        expected["nodes"][0]["data"]["node"]["template"]["text"]["value"] = "new"
        self.assertEqual(changed, expected)

    async def test_rejected_expired_stale_and_revoked_never_edit(self):
        for outcome in ("rejected", "expired", "stale", "revoked"):
            with self.subTest(outcome=outcome):
                request = self.request.model_copy(update={"operation_key": outcome})
                proposal = await self.actions.propose(self.context, request)
                if outcome == "expired":
                    async with self.store.transaction() as session:
                        row = await session.get(
                            AssistantGraphAction, UUID(proposal["id"])
                        )
                        row.expires_at = 0
                        session.add(row)
                elif outcome == "stale":
                    async with self.store.transaction() as session:
                        row = await session.get(Flow, self.flow_id)
                        row.name = "Editor saved"
                        session.add(row)
                elif outcome == "revoked":
                    await self.store.revoke("fixture")
                if outcome == "revoked":
                    with self.assertRaises(AssistantError):
                        await self.decide(proposal)
                else:
                    result, _, _ = await self.decide(
                        proposal, "reject" if outcome == "rejected" else "approve"
                    )
                    self.assertEqual(result["state"], outcome)
                async with self.store.transaction() as session:
                    row = await session.get(Flow, self.flow_id)
                    self.assertEqual(row.data, self.original)
                    row.name = "Existing graph"
                    session.add(row)

    async def test_action_key_digest_owner_and_session_are_bound(self):
        proposal = await self.actions.propose(self.context, self.request)
        with self.assertRaisesRegex(AssistantError, "assistant_action_conflict"):
            await self.actions.propose(
                self.context,
                self.request.model_copy(update={"changes": GraphChanges(name="Other")}),
            )
        with self.assertRaises(AssistantError):
            await self.actions.read(uuid4(), self.conversation, UUID(proposal["id"]))
        allowed = await self.actions.list(
            self.owner, self.conversation, session_key="fixture"
        )
        different = await self.actions.list(
            self.owner, self.conversation, session_key="other-session"
        )
        self.assertTrue(allowed[0]["can_decide"])
        self.assertFalse(different[0]["can_decide"])
        native_read = await self.actions.read(
            self.owner,
            self.conversation,
            UUID(proposal["id"]),
            session_key="other-session",
        )
        self.assertFalse(native_read["can_decide"])
        await self.store.admit_session("other-session", self.owner, time.time() + 1000)
        with self.assertRaises(AssistantError):
            await self.decide(proposal, key="other-session")

    async def test_run_is_claimed_once_with_exact_snapshot_and_server_session(self):
        request = GraphActionRequest(
            operation_key="run",
            kind="run",
            workflow_id=self.flow_id,
            expected_revision=self.revision,
            input_value="Hello",
        )
        proposal = await self.actions.propose(self.context, request)
        result, snapshot, actor = await self.decide(proposal)
        self.assertEqual(result["state"], "executing")
        self.assertEqual(snapshot.data, self.original)
        again, duplicate, _ = await self.decide(proposal)
        self.assertIsNone(duplicate)
        self.assertEqual(again, result)
        execute = AsyncMock()
        with patch("langflow.api.v1.endpoints.simple_run_flow", new=execute):
            await self.actions.execute(result, snapshot, actor, AsyncMock())
        call = execute.call_args
        self.assertEqual(call.args[1].session_id, "assistant-action-" + proposal["id"])
        self.assertEqual(call.args[1].output_type, "any")
        self.assertIsNone(call.args[1].tweaks)
        self.assertEqual(call.kwargs["run_id"], result["run_id"])
        self.assertEqual(call.kwargs["context"], {})
        self.assertEqual(
            (
                await self.actions.read(
                    self.owner, self.conversation, UUID(result["id"])
                )
            )["state"],
            "succeeded",
        )

    async def test_restart_observes_job_without_redispatch(self):
        request = GraphActionRequest(
            operation_key="run",
            kind="run",
            workflow_id=self.flow_id,
            expected_revision=self.revision,
        )
        proposal = await self.actions.propose(self.context, request)
        result, _, _ = await self.decide(proposal)
        jobs = AsyncMock()
        jobs.get_job_by_job_id.return_value = None
        with (
            patch("langflow.services.deps.get_job_service", return_value=jobs),
            patch(
                "langflow.api.v1.endpoints.simple_run_flow", new=AsyncMock()
            ) as execute,
        ):
            await self.actions.reconcile()
            execute.assert_not_called()
        self.assertEqual(
            (
                await self.actions.read(
                    self.owner, self.conversation, UUID(result["id"])
                )
            )["state"],
            "unknown",
        )

    async def test_code_and_secret_updates_refuse_and_node_removal_preserves_other_bytes(
        self,
    ):
        for field in ("code", "api_key"):
            with self.subTest(field=field), self.assertRaises(AssistantError):
                GraphEditor(self.catalog).apply(
                    self.original,
                    GraphChanges.model_validate(
                        {"updates": [{"node_id": "Text-one", "fields": {field: "BAD"}}]}
                    ),
                )
        data = deepcopy(self.original)
        data["edges"] = [{"source": "Text-one", "target": "Text-two", "id": "attached"}]
        changed, preview = GraphEditor(self.catalog).apply(
            data, GraphChanges(remove_nodes=["Text-one"])
        )
        self.assertEqual(changed["nodes"], [self.original["nodes"][1]])
        self.assertEqual(changed["edges"], [])
        self.assertIn("1 incident connections", str(preview))

    async def test_move_preserves_graph_and_requires_edit_approval(self):
        original = deepcopy(self.original)
        changes = GraphChanges.model_validate(
            {
                "name": "Layout",
                "positions": [{"node_id": "Text-one", "x": 120, "y": -50}],
            }
        )
        request = self.request.model_copy(update={"changes": changes})
        self.assertEqual(request.category, "edit")
        changed, preview = GraphEditor(self.catalog).apply(original, changes)
        self.assertEqual(changed["nodes"][0]["position"], {"x": 120, "y": -50})
        self.assertEqual(changed["nodes"][1:], original["nodes"][1:])
        self.assertEqual(changed["edges"], original["edges"])
        self.assertEqual(self.original, original)
        self.assertIn("Move Text-one", str(preview))
        projected = self.catalog.project(changed)
        self.assertEqual(projected["nodes"][0]["position"], {"x": 120, "y": -50})
        with self.assertRaises(AssistantError):
            GraphEditor(self.catalog).apply(
                original,
                GraphChanges.model_validate(
                    {
                        "positions": [
                            {"node_id": "Text-one", "x": 1, "y": 2},
                            {"node_id": "Text-one", "x": 3, "y": 4},
                        ]
                    }
                ),
            )
        with self.assertRaises(AssistantError):
            GraphEditor(self.catalog).apply(
                original,
                GraphChanges.model_validate(
                    {"positions": [{"node_id": "missing", "x": 1, "y": 2}]}
                ),
            )
        with self.assertRaises(ValueError):
            GraphChanges.model_validate(
                {"positions": [{"node_id": "Text-one", "x": float("inf"), "y": 0}]}
            )

    async def test_name_conflict_is_definite_and_leaves_original_graph_unchanged(self):
        async with self.store.transaction() as session:
            session.add(Flow(name="Taken", data=self.original, user_id=self.owner))
        proposal = await self.actions.propose(
            self.context,
            self.request.model_copy(update={"changes": GraphChanges(name="Taken")}),
        )
        result, snapshot, _ = await self.decide(proposal)
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["error_code"], "assistant_graph_name_conflict")
        self.assertIsNone(snapshot)
        async with self.store.sessions() as session:
            flow = await session.get(Flow, self.flow_id)
            self.assertEqual(flow.name, "Existing graph")
            self.assertEqual(flow.data, self.original)

    async def test_revocation_before_dispatch_records_not_started(self):
        request = GraphActionRequest(
            operation_key="run",
            kind="run",
            workflow_id=self.flow_id,
            expected_revision=self.revision,
        )
        proposal = await self.actions.propose(self.context, request)
        result, snapshot, actor = await self.decide(proposal)
        with patch(
            "langflow.api.v1.endpoints.simple_run_flow", new=AsyncMock()
        ) as execute:
            await self.actions.execute(
                result,
                snapshot,
                actor,
                AsyncMock(side_effect=AssistantError("assistant_session_locked", 403)),
            )
            execute.assert_not_called()
        observed = await self.actions.read(
            self.owner, self.conversation, UUID(result["id"])
        )
        self.assertEqual(observed["state"], "not_dispatched")
        self.assertEqual(observed["error_code"], "assistant_action_not_dispatched")

    async def test_resource_revocation_after_approval_prevents_dispatch(self):
        from types import SimpleNamespace

        request = GraphActionRequest(
            operation_key="resource-fence",
            kind="run",
            workflow_id=self.flow_id,
            expected_revision=self.revision,
        )
        proposal = await self.actions.propose(self.context, request)
        result, snapshot, actor = await self.decide(proposal)
        self.actions.configuration = SimpleNamespace(
            check_graph=AsyncMock(
                side_effect=AssistantError("provider_connection_changed")
            )
        )
        with patch(
            "langflow.api.v1.endpoints.simple_run_flow", new=AsyncMock()
        ) as execute:
            await self.actions.execute(result, snapshot, actor, AsyncMock())
            execute.assert_not_called()
        observed = await self.actions.read(
            self.owner, self.conversation, UUID(result["id"])
        )
        self.assertEqual(observed["state"], "not_dispatched")

    async def test_cancellation_before_dispatch_is_definitely_not_started(self):
        request = GraphActionRequest(
            operation_key="cancel-before-dispatch",
            kind="run",
            workflow_id=self.flow_id,
            expected_revision=self.revision,
        )
        proposal = await self.actions.propose(self.context, request)
        result, snapshot, actor = await self.decide(proposal)
        with patch(
            "langflow.api.v1.endpoints.simple_run_flow", new=AsyncMock()
        ) as execute:
            with self.assertRaises(asyncio.CancelledError):
                await self.actions.execute(
                    result,
                    snapshot,
                    actor,
                    AsyncMock(
                        side_effect=asyncio.CancelledError("LANGFLOW_USER_CANCELLED")
                    ),
                )
            execute.assert_not_called()
        observed = await self.actions.read(
            self.owner, self.conversation, UUID(result["id"])
        )
        self.assertEqual(observed["state"], "not_dispatched")
        self.assertEqual(observed["error_code"], "assistant_action_not_dispatched")

    async def test_edit_can_repair_a_graph_without_using_its_stale_run_binding(self):
        from types import SimpleNamespace

        proposal = await self.actions.propose(self.context, self.request)
        self.actions.configuration = SimpleNamespace(
            check_graph=AsyncMock(
                side_effect=AssistantError("provider_connection_changed")
            ),
            prepare=AsyncMock(),
        )
        result, snapshot, _ = await self.decide(proposal)
        self.assertEqual(result["state"], "succeeded")
        self.assertIsNone(snapshot)
        self.actions.configuration.check_graph.assert_not_awaited()
        self.actions.configuration.prepare.assert_awaited_once()

    async def test_typed_run_inputs_are_digest_bound_and_never_mutate_the_saved_graph(
        self,
    ):
        from laomedo.integrations.langflow.assistant.models import GraphRunInput

        request = GraphActionRequest(
            operation_key="runtime-input",
            kind="run",
            workflow_id=self.flow_id,
            expected_revision=self.revision,
            node_inputs=[
                GraphRunInput(node_id="Text-one", field="text", value="runtime")
            ],
            output_component="Text-one",
        )
        result = self.actions.run_data(self.original, request)
        self.assertEqual(
            result["nodes"][0]["data"]["node"]["template"]["text"]["value"], "runtime"
        )
        self.assertEqual(
            self.original["nodes"][0]["data"]["node"]["template"]["text"]["value"],
            "old",
        )
        self.assertNotEqual(
            request.digest(),
            request.model_copy(update={"output_component": "Text-two"}).digest(),
        )
        bad = request.model_copy(
            update={
                "node_inputs": [
                    GraphRunInput(node_id="Text-one", field="api_key", value="refused")
                ]
            }
        )
        with self.assertRaises(AssistantError):
            self.actions.run_data(self.original, bad)

    async def test_concurrent_run_approvals_return_one_dispatch_snapshot(self):
        request = GraphActionRequest(
            operation_key="concurrent-run",
            kind="run",
            workflow_id=self.flow_id,
            expected_revision=self.revision,
        )
        proposal = await self.actions.propose(self.context, request)
        decisions = await asyncio.gather(self.decide(proposal), self.decide(proposal))
        self.assertEqual(sum(snapshot is not None for _, snapshot, _ in decisions), 1)
        self.assertEqual(decisions[0][0]["run_id"], decisions[1][0]["run_id"])

    async def test_recovery_accepts_only_exact_owned_terminal_jobs(self):
        from types import SimpleNamespace

        for case in ("completed", "failed", "wrong-owner", "wrong-flow"):
            with self.subTest(case=case):
                request = GraphActionRequest(
                    operation_key=case,
                    kind="run",
                    workflow_id=self.flow_id,
                    expected_revision=self.revision,
                )
                proposal = await self.actions.propose(self.context, request)
                result, _, _ = await self.decide(proposal)
                job = SimpleNamespace(
                    user_id=uuid4() if case == "wrong-owner" else self.owner,
                    flow_id=uuid4() if case == "wrong-flow" else self.flow_id,
                    status="failed" if case == "failed" else "completed",
                )
                jobs = AsyncMock()
                jobs.get_job_by_job_id.return_value = job
                with (
                    patch("langflow.services.deps.get_job_service", return_value=jobs),
                    patch(
                        "langflow.api.v1.endpoints.simple_run_flow", new=AsyncMock()
                    ) as execute,
                ):
                    await self.actions.reconcile(UUID(result["id"]))
                    execute.assert_not_called()
                observed = await self.actions.read(
                    self.owner, self.conversation, UUID(result["id"])
                )
                self.assertEqual(
                    observed["state"],
                    (
                        "succeeded"
                        if case == "completed"
                        else "failed" if case == "failed" else "unknown"
                    ),
                )

    async def test_connections_cannot_bypass_raw_credential_or_host_field_rules(self):
        from laomedo.integrations.langflow.assistant.models import GraphConnection

        for field in ("api_key", "runner_url", "file_path"):
            with self.subTest(field=field):
                snapshot = {
                    "test": {
                        "String": {
                            "template": {
                                "code": {"value": "TRUSTED_CODE"},
                                field: {"type": "str", "value": None},
                            },
                            "outputs": [{"name": "text", "types": ["str"]}],
                        }
                    }
                }
                catalog = ComponentCatalog(snapshot)
                data, _ = catalog.compile(
                    DraftGraph(
                        nodes=[
                            DraftNode(key="one", component_type="test/String"),
                            DraftNode(key="two", component_type="test/String"),
                        ],
                        allow_incomplete=True,
                    )
                )
                with self.assertRaises(AssistantError):
                    GraphEditor(catalog).apply(
                        data,
                        GraphChanges(
                            connect=[
                                GraphConnection(
                                    source="String-one",
                                    output="text",
                                    target="String-two",
                                    input=field,
                                )
                            ]
                        ),
                    )
