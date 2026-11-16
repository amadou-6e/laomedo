"""Real Flow/database atomicity, stale edits, receipts and bounded projections."""

import asyncio
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from langflow.services.database.models.flow.model import Flow
from langflow.services.database.models.user.model import User
from langflow.services.database.models.folder.model import Folder
from langflow.services.database.models.folder.constants import DEFAULT_FOLDER_NAME

from laomedo.integrations.langflow.assistant.catalog import ComponentCatalog
from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.models import (
    AuthoringContext,
    ConversationRequest,
    MessageRequest,
    DraftRequest,
    AssistantDraftReceipt,
)
from laomedo.integrations.langflow.assistant.persistence import AssistantStore
from laomedo.integrations.langflow.assistant.workflows import WorkflowDrafts


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
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
                    id=self.owner,
                    username="owner",
                    password="unused-fixture-hash",
                    is_active=True,
                )
            )
            session.add(Folder(name=DEFAULT_FOLDER_NAME, user_id=self.owner))
        await self.store.admit_session("fixture", self.owner, time.time() + 1000)
        conversation = await self.store.create(
            self.owner,
            ConversationRequest(model="fixture", effort="low"),
            session_key="fixture",
        )
        self.identifier = UUID(conversation["id"])
        message, _ = await self.store.reserve(
            self.owner,
            self.identifier,
            MessageRequest(client_message_id=uuid4(), text="Make a draft"),
            session_key="fixture",
        )
        self.context = AuthoringContext(
            owner_id=self.owner,
            conversation_id=self.identifier,
            message_id=message["id"],
            attempt_id=message["attempt_id"],
            session_key="fixture",
        )
        self.catalog = ComponentCatalog(
            {
                "test": {
                    "Text": {
                        "template": {
                            "code": {"value": "TRUSTED_CODE"},
                            "text": {"type": "str", "required": True, "value": ""},
                            "api_key": {
                                "type": "str",
                                "password": True,
                                "value": "SECRET_CANARY",
                            },
                        },
                        "outputs": [{"name": "text", "types": ["Message"]}],
                    }
                }
            }
        )
        self.authorize = AsyncMock()
        self.workflows = WorkflowDrafts(self.store, self.catalog, self.authorize)
        self.request = DraftRequest.model_validate(
            {
                "draft_key": "first",
                "name": "My draft",
                "spec": {
                    "allow_incomplete": True,
                    "nodes": [
                        {
                            "key": "text",
                            "component_type": "test/Text",
                            "fields": {"text": "Hello"},
                        }
                    ],
                },
            }
        )

    async def asyncTearDown(self):
        await self.engine.dispose()
        self.directory.cleanup()

    async def test_save_is_atomic_idempotent_and_does_not_enable_execution(self):
        receipt = await self.workflows.save(self.context, self.request)
        again = await self.workflows.save(self.context, self.request)
        self.assertEqual(receipt, again)
        async with self.store.sessions() as session:
            flows = (
                await session.exec(select(Flow).where(Flow.user_id == self.owner))
            ).all()
            receipts = (await session.exec(select(AssistantDraftReceipt))).all()
        self.assertEqual(len(flows), 1)
        self.assertEqual(len(receipts), 1)
        self.assertFalse(flows[0].mcp_enabled)
        self.assertFalse(flows[0].webhook)
        self.assertFalse(flows[0].a2a_enabled)
        self.assertIsNone(flows[0].fs_path)
        projected = await self.workflows.get(self.context, flows[0].id)
        self.assertNotIn("SECRET_CANARY", str(projected))
        self.assertNotIn("TRUSTED_CODE", str(projected))
        with self.assertRaisesRegex(AssistantError, "assistant_draft_key_conflict"):
            await self.workflows.save(
                self.context, self.request.model_copy(update={"name": "Changed"})
            )

    async def test_concurrent_edits_compare_revision_inside_database_transaction(self):
        receipt = await self.workflows.save(self.context, self.request)
        edit = self.request.model_copy(
            update={
                "draft_key": "edit",
                "draft_id": UUID(receipt["workflow_id"]),
                "expected_revision": receipt["revision"],
                "name": "Edited",
            }
        )
        results = await asyncio.gather(
            self.workflows.save(self.context, edit),
            self.workflows.save(
                self.context,
                edit.model_copy(update={"draft_key": "rival", "name": "Rival"}),
            ),
            return_exceptions=True,
        )
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        errors = [result for result in results if isinstance(result, AssistantError)]
        self.assertEqual(
            [error.code for error in errors], ["assistant_draft_revision_changed"]
        )

    async def test_editor_change_refuses_and_source_workflow_cannot_be_updated(self):
        receipt = await self.workflows.save(self.context, self.request)
        identifier = UUID(receipt["workflow_id"])
        async with self.store.transaction() as session:
            flow = await session.get(Flow, identifier)
            flow.name = "Edited in the editor"
            session.add(flow)
            source = Flow(
                name="Existing source",
                user_id=self.owner,
                data={"nodes": [], "edges": []},
            )
            session.add(source)
            await session.flush()
            source_id = source.id
        edit = self.request.model_copy(
            update={
                "draft_key": "edit",
                "draft_id": identifier,
                "expected_revision": receipt["revision"],
            }
        )
        with self.assertRaisesRegex(AssistantError, "assistant_draft_revision_changed"):
            await self.workflows.save(self.context, edit)
        with self.assertRaisesRegex(AssistantError, "assistant_draft_not_owned"):
            await self.workflows.save(
                self.context, edit.model_copy(update={"draft_id": source_id})
            )

    async def test_lost_commit_ack_reconciles_original_receipt_without_duplicate_flow(
        self,
    ):
        original = AsyncSession.commit

        async def lost_ack(session):
            await original(session)
            raise SQLAlchemyError("fixture lost commit acknowledgement")

        with patch.object(AsyncSession, "commit", lost_ack):
            with self.assertRaisesRegex(
                AssistantError, "assistant_save_outcome_unknown"
            ):
                await self.workflows.save(self.context, self.request)
        receipt = await self.workflows.save(self.context, self.request)
        self.assertEqual(receipt["draft_key"], "first")
        self.assertEqual(len((await self.workflows.list(self.context))["workflows"]), 1)

    async def test_revocation_refuses_save_without_creating_flow_or_receipt(self):
        await self.store.revoke("fixture")
        with self.assertRaisesRegex(AssistantError, "assistant_session_locked"):
            await self.workflows.save(self.context, self.request)
        async with self.store.sessions() as session:
            self.assertEqual((await session.exec(select(Flow))).all(), [])
            self.assertEqual(
                (await session.exec(select(AssistantDraftReceipt))).all(), []
            )

    async def test_failure_after_flow_flush_rolls_back_flow_and_receipt(self):
        self.authorize.side_effect = [
            None,
            None,
            AssistantError("assistant_tool_authority_revoked", 403),
        ]
        with self.assertRaisesRegex(AssistantError, "assistant_tool_authority_revoked"):
            await self.workflows.save(self.context, self.request)
        async with self.store.sessions() as session:
            self.assertEqual((await session.exec(select(Flow))).all(), [])
            self.assertEqual(
                (await session.exec(select(AssistantDraftReceipt))).all(), []
            )

    async def test_other_owner_cannot_inspect_or_copy_a_source(self):
        other = uuid4()
        async with self.store.transaction() as session:
            session.add(
                User(id=other, username="other", password="fixture", is_active=True)
            )
            source = Flow(
                name="Private source", user_id=other, data={"nodes": [], "edges": []}
            )
            session.add(source)
            await session.flush()
            identifier, revision = source.id, self.workflows.revision(source)
        self.assertEqual((await self.workflows.list(self.context))["workflows"], [])
        with self.assertRaisesRegex(AssistantError, "assistant_workflow_not_found"):
            await self.workflows.get(self.context, identifier)
        from laomedo.integrations.langflow.assistant.models import WorkflowSource

        with self.assertRaisesRegex(
            AssistantError, "assistant_source_revision_changed"
        ):
            await self.workflows.save(
                self.context,
                self.request.model_copy(
                    update={
                        "sources": [
                            WorkflowSource(workflow_id=identifier, revision=revision)
                        ]
                    }
                ),
            )
