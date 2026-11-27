"""Authenticated canvas streaming over the same isolated graph execution owner."""

import asyncio
from copy import deepcopy
from functools import partial
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException, Request
from langflow.services.auth.utils import get_current_active_user
from lfx.schema.workflow import (
    WorkflowRunRequest,
    WorkflowStopRequest,
    WorkflowStopResponse,
)
from lfx.workflow.adapters import StreamAdapterContext, get_stream_adapter
from starlette.responses import StreamingResponse
from anyio import CancelScope

from langflow.api.v1.schemas import SimplifiedAPIRequest
from laomedo.agents.connections.errors import ProviderConnectionError
from laomedo.agents.errors import RunnerError
from laomedo.agents.interface.models import RunnerDiagnostics
from laomedo.integrations.langflow.execution.providers.models import ProviderCanvasJob
from laomedo.integrations.langflow.execution.providers.settings import (
    PROVIDER_PROGRESS_QUEUE_SIZE,
)
from laomedo.integrations.langflow.execution.worker.errors import GraphWorkerError


class ProviderCanvasRoutes:
    """Own browser HTTP tasks only; native authority stays in ProviderGraphExecutor."""

    def __init__(self, origin, executor):
        self.origin, self.executor = origin, executor
        self.jobs = {}

    async def payload(self, request, model):
        """Require the explicit same-origin browser and bound the body before parsing."""
        if (
            request.headers.get("origin") != self.origin
            or str(request.base_url).rstrip("/") != self.origin
            or request.headers.get("sec-fetch-site") not in (None, "same-origin")
        ):
            raise HTTPException(403, detail={"code": "provider_request_refused"})
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 16 * 1024 * 1024:
                raise HTTPException(413, detail={"code": "assistant_input_invalid"})
        try:
            return model.model_validate_json(bytes(data))
        except ValueError:
            raise HTTPException(
                422, detail={"code": "assistant_input_invalid"}
            ) from None

    @staticmethod
    def through(graph, target):
        """Run a selected component and its upstream dependencies, never its dependents."""
        graph = deepcopy(graph)
        nodes = {node["id"]: node for node in graph["nodes"]}
        if target not in nodes:
            raise ValueError
        selected, pending = set(), {target}
        while pending:
            selected.update(pending)
            pending = {
                edge["source"]
                for edge in graph["edges"]
                if edge["target"] in selected and edge["source"] not in selected
            }
        graph["nodes"] = [node for node in graph["nodes"] if node["id"] in selected]
        graph["edges"] = [
            edge
            for edge in graph["edges"]
            if edge["source"] in selected and edge["target"] in selected
        ]
        return graph

    async def snapshot(self, owner, payload):
        """Read an owned Flow and authorize execution before considering a canvas override."""
        from langflow.services.database.models.flow.model import Flow, FlowRead
        from langflow.services.deps import session_scope
        from langflow.services.authorization import FlowAction, ensure_flow_permission
        from langflow.api.v1.flows import _validate_catalog_policy_for_write
        from langflow.services.deps import get_catalog_policy_service

        identifier = UUID(payload.flow_id)
        async with session_scope() as session:
            flow = await session.get(Flow, identifier)
            if flow is None or flow.user_id != UUID(str(owner.id)):
                raise HTTPException(404, detail="Not Found")
            await ensure_flow_permission(
                owner,
                FlowAction.EXECUTE,
                flow_id=flow.id,
                flow_user_id=flow.user_id,
                workspace_id=flow.workspace_id,
                folder_id=flow.folder_id,
            )
            snapshot = FlowRead.model_validate(flow, from_attributes=True).model_copy(
                deep=True
            )
        graph = payload.data if payload.data is not None else snapshot.data
        if payload.stop_component_id:
            graph = self.through(graph, payload.stop_component_id)
        _validate_catalog_policy_for_write(
            graph, snapshot=get_catalog_policy_service().snapshot
        )
        graph = self.executor.admission.input_graph(graph, payload.input_value, "text")
        self.executor.validate_graph(UUID(str(owner.id)), identifier, graph)
        return snapshot.model_copy(update={"data": graph}, deep=True)

    async def run(self, request: Request, user=Depends(get_current_active_user)):
        """Serve only fresh isolated runs on the existing canvas's AG-UI protocol."""
        payload = await self.payload(request, WorkflowRunRequest)
        if (
            str(payload.mode.value) != "stream"
            or payload.stream_protocol != "agui"
            or payload.tweaks
            or payload.globals
            or payload.files
            or payload.start_component_id
            or payload.output_ids
            or payload.idempotency_key
        ):
            raise HTTPException(422, detail={"code": "isolated_graph_unsupported"})
        try:
            snapshot = await self.snapshot(user, payload)
        except (ValueError, KeyError, GraphWorkerError, ProviderConnectionError):
            raise HTTPException(
                422, detail={"code": "isolated_graph_unsupported"}
            ) from None
        identifier = uuid4()
        action = SimplifiedAPIRequest(
            input_type="text",
            output_component=payload.stop_component_id or "",
        )
        adapter = get_stream_adapter(
            "agui",
            StreamAdapterContext(
                run_id=str(identifier),
                thread_id=payload.session_id or str(identifier),
                expose_graph_state=payload.expose_graph_state is not False,
            ),
        )
        return ProviderCanvasResponse(
            self.events(snapshot, action, user, identifier, adapter),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @staticmethod
    def frames(events):
        """Use the installed protocol adapter's JSON, without a second AG-UI schema."""
        return b"".join(
            ("data: " + event.data_json + "\n\n").encode() for event in events
        )

    async def events(self, snapshot, action, user, identifier, adapter):
        """Stream actual worker observations; a terminal message still needs host completion."""
        queue = ProviderCanvasProgress()
        task = asyncio.create_task(
            self.executor.execute(
                snapshot,
                action,
                user,
                identifier,
                on_event=queue.put_nowait,
            )
        )
        self.jobs[identifier] = ProviderCanvasJob(
            owner_id=UUID(str(user.id)), task=task
        )
        task.add_done_callback(partial(self.settled, identifier))
        try:
            yield self.frames(adapter.initial_events())
            yield self.frames(
                adapter.translate(
                    "vertices_sorted",
                    {"to_run": [node["id"] for node in snapshot.data["nodes"]]},
                )
            )
            while not task.done() or not queue.empty():
                try:
                    event = await asyncio.wait_for(queue.get(), 1)
                except asyncio.TimeoutError:
                    yield b": keep-alive\n\n"
                    continue
                yield self.frames(adapter.translate(event.event, event.data))
            if queue.dropped:
                yield self.frames(
                    adapter.translate(
                        "warning",
                        {
                            "message": "Some progress updates were not captured. Run results are unchanged.",
                            "dropped_updates": queue.dropped,
                        },
                    )
                )
            if task.cancelled():
                yield self.frames(adapter.cancel_events("Cancellation requested."))
            elif task.exception() is not None:
                code = RunnerDiagnostics.safe_code(
                    getattr(task.exception(), "code", None)
                )
                yield self.frames(
                    adapter.error_events(
                        RunnerError(code) if code else GraphWorkerError()
                    )
                )
            else:
                yield self.frames(adapter.translate("end", {}))
                yield self.frames(adapter.final_events())
        finally:
            if not task.done():
                task.cancel()
            with CancelScope(shield=True):
                await asyncio.shield(asyncio.gather(task, return_exceptions=True))
            self.settled(identifier, task)

    def settled(self, identifier, task):
        """Remove the receipt independently of response-generator finalization."""
        self.jobs.pop(identifier, None)

    async def stop(self, request: Request, user=Depends(get_current_active_user)):
        """Cancel only this authenticated owner's exact active local canvas task."""
        payload = await self.payload(request, WorkflowStopRequest)
        owner, identifier = UUID(str(user.id)), UUID(str(payload.job_id))
        self.executor.browser(owner)
        receipt = self.jobs.get(identifier)
        if receipt is None or receipt.owner_id != owner:
            raise HTTPException(404, detail="Not Found")
        receipt.task.cancel()
        return WorkflowStopResponse(
            job_id=identifier, message="Cancellation requested."
        )

    def install(self, app):
        """Mount the two explicit trusted adapters before the unknown-API fallback."""
        app.add_api_route("/api/v2/workflows", self.run, methods=["POST"])
        app.add_api_route("/api/v2/workflows/stop", self.stop, methods=["POST"])


class ProviderCanvasProgress(asyncio.Queue):
    """Bounded best-effort observation; client backpressure never stops execution."""

    def __init__(self):
        super().__init__(maxsize=PROVIDER_PROGRESS_QUEUE_SIZE)
        self.dropped = 0

    def put_nowait(self, event):
        try:
            super().put_nowait(event)
        except asyncio.QueueFull:
            self.dropped += 1


class ProviderCanvasResponse(StreamingResponse):
    """Close the execution generator explicitly when the ASGI send disconnects."""

    async def stream_response(self, send):
        try:
            await super().stream_response(send)
        finally:
            with CancelScope(shield=True):
                await self.body_iterator.aclose()
