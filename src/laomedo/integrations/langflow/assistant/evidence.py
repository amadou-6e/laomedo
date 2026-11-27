"""Bounded intended run outputs under the existing assistant database authority."""

import json
import re
from itertools import islice
from uuid import UUID

from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.models import AssistantRunEvidence
from laomedo.integrations.langflow.assistant.models import WorkflowNodeOutput
from laomedo.integrations.langflow.assistant.models import WorkflowRunResult
from laomedo.integrations.langflow.assistant.models import WorkflowNodeStatus
from laomedo.integrations.langflow.assistant.models import FlowDiagnostic
from laomedo.integrations.langflow.assistant.settings import RUN_OUTPUT_BYTES
from laomedo.integrations.langflow.assistant.settings import RUN_OUTPUT_ITEMS


class WorkflowRunEvidence:
    """Retain only explicit node outputs; never serialize input, artifacts or raw logs."""

    def __init__(self, actions):
        """Reuse graph-action ownership and its original database lifecycle."""
        self.actions = actions

    async def node_status(self, context, action):
        """Read only status columns after verifying the execution owner's exact job."""
        from langflow.services.deps import get_job_service
        from langflow.services.database.models.vertex_builds.model import (
            VertexBuildTable,
        )
        from sqlmodel import select

        if action["run_id"] is None:
            return []
        try:
            job = await get_job_service().get_job_by_job_id(
                UUID(action["run_id"]), user_id=context.owner_id
            )
            if (
                job is None
                or job.user_id != context.owner_id
                or str(job.flow_id) != action["workflow_id"]
            ):
                return []
            metadata = getattr(job, "job_metadata", None) or {}
            if metadata.get("execution_owner") == "laomedo-isolated-provider":
                return [
                    WorkflowNodeStatus.model_validate(value)
                    for value in metadata.get("isolated_provider_nodes", [])[
                        :RUN_OUTPUT_ITEMS
                    ]
                ]
            async with self.actions.store.sessions() as session:
                rows = (
                    await session.exec(
                        select(VertexBuildTable.id, VertexBuildTable.valid)
                        .where(
                            VertexBuildTable.job_id == UUID(action["run_id"]),
                            VertexBuildTable.flow_id == job.flow_id,
                        )
                        .order_by(
                            VertexBuildTable.timestamp.desc(),
                            VertexBuildTable.build_id.desc(),
                        )
                        .limit(RUN_OUTPUT_ITEMS)
                    )
                ).all()
            latest = {}
            for node_id, valid in rows:
                if node_id not in latest and len(latest) < 100:
                    latest[node_id] = WorkflowNodeStatus(
                        node_id=node_id, state="succeeded" if valid else "failed"
                    )
            return list(latest.values())
        except Exception:
            # No exact-run observations means unavailable, never a flow-wide or raw-error fallback.
            return []

    @classmethod
    def safe_value(cls, value, depth=0):
        """Bound JSON output and omit sensitive structural keys; never invoke serializers."""
        if depth > 5:
            raise ValueError("output_depth")
        if value is None or type(value) in (bool, int, float):
            return value
        if isinstance(value, str):
            if len(value) > RUN_OUTPUT_BYTES:
                raise ValueError("output_size")
            return re.sub(
                r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+|\bsk-[A-Za-z0-9_-]{12,}",
                "[redacted]",
                value,
            )
        if type(value) is list and len(value) <= RUN_OUTPUT_ITEMS:
            return [cls.safe_value(item, depth + 1) for item in value]
        if type(value) is dict and len(value) <= RUN_OUTPUT_ITEMS:
            return {
                key: cls.safe_value(item, depth + 1)
                for key, item in value.items()
                if isinstance(key, str)
                and len(key) <= 100
                and not re.search(
                    r"(?i)password|secret|token|api.?key|credential|authorization|stack.?trace|headers|^code$",
                    key,
                )
            }
        raise ValueError("output_type")

    async def retain(self, action, response, *, data=None):
        """Persist intended RunResponse outputs without following arbitrary nested model state."""
        from lfx.graph.schema import RunOutputs, ResultData
        from lfx.schema.data import Data
        from lfx.schema.message import Message
        from langflow.api.v1.schemas import RunResponse

        if not isinstance(response, RunResponse):
            return False
        outputs, size, truncated = [], 0, False
        groups = getattr(response, "outputs", []) or []
        truncated = len(groups) > RUN_OUTPUT_ITEMS
        visited = 0
        for group in islice(groups, RUN_OUTPUT_ITEMS):
            if not isinstance(group, RunOutputs):
                truncated = True
                continue
            truncated = truncated or len(group.outputs) > RUN_OUTPUT_ITEMS
            for node in islice(group.outputs, RUN_OUTPUT_ITEMS):
                if not isinstance(node, ResultData) or not isinstance(
                    node.results, dict
                ):
                    truncated = True
                    continue
                truncated = truncated or len(node.results) > RUN_OUTPUT_ITEMS
                for name, value in islice(node.results.items(), RUN_OUTPUT_ITEMS):
                    visited += 1
                    if visited > RUN_OUTPUT_ITEMS:
                        truncated = True
                        break
                    try:
                        # Message private properties/metadata never enter this projection.
                        if isinstance(value, Message):
                            value = value.text
                        elif isinstance(value, Data):
                            value = value.data
                        projected = WorkflowNodeOutput(
                            node_id=node.component_id or "unknown",
                            output=name,
                            value=self.safe_value(value),
                        ).model_dump(mode="json")
                        encoded = json.dumps(projected, allow_nan=False).encode()
                        if (
                            len(outputs) >= RUN_OUTPUT_ITEMS
                            or size + len(encoded) > RUN_OUTPUT_BYTES
                        ):
                            raise ValueError("output_limit")
                    except (ValueError, TypeError, OverflowError):
                        truncated = True
                        continue
                    outputs.append(projected)
                    size += len(encoded)
                if visited > RUN_OUTPUT_ITEMS:
                    break
            if visited > RUN_OUTPUT_ITEMS:
                break
        async with self.actions.store.transaction() as session:
            from laomedo.integrations.langflow.assistant.models import (
                AssistantGraphAction,
            )

            row = await session.get(AssistantGraphAction, UUID(action["id"]))
            if row is None or row.kind != "run" or str(row.run_id) != action["run_id"]:
                raise AssistantError("assistant_workflow_not_found", 404)
            existing = await session.get(AssistantRunEvidence, row.id)
            if existing is None:
                session.add(
                    AssistantRunEvidence(
                        action_id=row.id,
                        owner_id=row.owner_id,
                        conversation_id=row.conversation_id,
                        workflow_id=row.workflow_id,
                        run_id=row.run_id,
                        revision=row.revision,
                        outputs=outputs,
                        bindings=(
                            self.actions.configuration.graph_bindings(
                                self.actions.catalog, data
                            )
                            if self.actions.configuration is not None
                            else []
                        ),
                        truncated=truncated,
                    )
                )
        return True

    async def read(self, context, identifier, *, node_id=None, cursor=0):
        """Release only exact owned evidence under current browser authority, with paging."""
        if cursor < 0 or cursor > RUN_OUTPUT_ITEMS:
            raise AssistantError("assistant_input_invalid", 422)
        await self.actions.authorize(context)
        await self.actions.read(
            context.owner_id,
            context.conversation_id,
            identifier,
            session_key=context.session_key,
        )
        await self.actions.reconcile(identifier)
        action = await self.actions.read(
            context.owner_id,
            context.conversation_id,
            identifier,
            session_key=context.session_key,
        )
        if action["kind"] != "run":
            raise AssistantError("assistant_input_invalid", 422)
        async with self.actions.store.sessions() as session:
            await self.actions.store.authorize(
                session, context.owner_id, context.session_key
            )
            record = await session.get(AssistantRunEvidence, identifier)
            if record is not None and (
                record.owner_id != context.owner_id
                or record.conversation_id != context.conversation_id
            ):
                raise AssistantError("assistant_workflow_not_found", 404)
            values = (
                [
                    WorkflowNodeOutput.model_validate(value).model_dump(mode="json")
                    for value in record.outputs
                    if node_id is None or value["node_id"] == node_id
                ]
                if record
                else []
            )
            result = {
                "action_id": str(identifier),
                "workflow_id": action["workflow_id"],
                "revision": action["revision"],
                "run_id": action["run_id"],
                "state": action["state"],
                "error_code": action["error_code"],
                "output_available": bool(record and record.outputs),
                "outputs": values[cursor : cursor + 20],
                "next_cursor": cursor + 20 if len(values) > cursor + 20 else None,
                "truncated": record.truncated if record else False,
            }
            bindings = record.bindings if record else []
        if bindings:
            if self.actions.configuration is None:
                raise AssistantError("assistant_resource_unavailable", 409)
            await self.actions.configuration.check_bindings(
                context, self.actions.catalog, bindings
            )
        nodes = await self.node_status(context, action)
        result["nodes"] = [node.model_dump() for node in nodes]
        result["node_status_available"] = bool(nodes)
        result["diagnostics"] = [
            FlowDiagnostic(
                code="node_execution_failed",
                node_id=node.node_id,
                message="This node failed. Inspect its configuration and connected inputs.",
            ).model_dump()
            for node in nodes
            if node.state == "failed"
        ]
        await self.actions.authorize(context)
        return WorkflowRunResult.model_validate(result).model_dump(mode="json")
