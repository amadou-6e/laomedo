"""Saved-provider specialization of the shared isolated native worker supervisor."""

import asyncio
from io import BytesIO
import time

from laomedo.agents.connections.errors import ProviderConnectionError
from laomedo.github.node_runs.authority import GitHubRunAuthority
from laomedo.integrations.langflow.execution.worker.channel import GraphWorkerChannel
from laomedo.integrations.langflow.execution.worker.container import DockerGraphWorker
from laomedo.integrations.langflow.execution.worker.errors import GraphWorkerError
from laomedo.integrations.langflow.execution.worker.models import (
    GraphWorkerResult,
    GraphWorkerScope,
)
from laomedo.integrations.langflow.execution.providers.models import (
    ProviderWorkerCall,
    ProviderWorkerReply,
    ProviderWorkerEvent,
)
from laomedo.integrations.langflow.execution.providers.settings import (
    PROVIDER_WORKER_MODULE,
)


class DockerProviderGraphWorker(DockerGraphWorker):
    """Keep admission and native effects on the host side of a one-job pipe.

    One instance owns exactly one admitted job. It must remain retained when
    cleanup raises: its revoked receipt can then be reconciled without restoring
    the worker's authority. Container cleanup remains owned by the shared base.
    """

    worker_module = PROVIDER_WORKER_MODULE

    def __init__(self, settings, job, dispatcher):
        super().__init__(settings, None, None)
        self.job_id = job.job_id
        self.first_vertex = (
            dispatcher.plan.nodes[0].vertex_id
            if dispatcher.plan.nodes
            else job.graph["nodes"][0]["id"]
        )
        self.dispatcher = dispatcher
        self.plan = dispatcher.plan
        self._pending = set()
        self._shutdown = None
        self.stops = None
        self.on_event = None
        self.vertices = {node["id"] for node in job.graph["nodes"]}
        self._validate_graph(job)

    def _job_scope(self, job_id):
        if job_id != self.job_id:
            return None
        return GraphWorkerScope(
            owner_id=self.plan.profile_id,
            flow_id=self.plan.flow_id,
            graph_digest=self.dispatcher.worker_graph_digest,
            first_vertex=self.first_vertex,
        )

    def _remaining(self, job_id):
        if job_id != self.job_id or self._shutdown is not None:
            return None
        try:
            plan = self.dispatcher.controllers.graph_runs.plan(
                self.dispatcher.capability, self.dispatcher.graph_digest
            )
            return plan.deadline - time.monotonic()
        except ProviderConnectionError:
            return None

    def _validate_graph(self, job):
        if (
            job.job_id != self.job_id
            or job.flow_id != self.plan.flow_id
            or job.graph_digest != self.dispatcher.worker_graph_digest
            or GitHubRunAuthority.digest_graph(job.graph) != job.graph_digest
            or {route.vertex_id for route in job.providers}
            != {node.vertex_id for node in self.plan.nodes}
            or set(job.public_issues) != set(self.dispatcher.issues)
        ):
            raise GraphWorkerError()

    async def _authorize_job(self, job, first_vertex):
        if self._remaining(job.job_id) is None:
            raise GraphWorkerError()
        for node in self.plan.nodes:
            self.dispatcher.controllers.graph_runs.resolve(
                self.dispatcher.capability, self.plan.graph_digest, node.vertex_id
            )

    def _revoke_job(self, job_id):
        if job_id != self.job_id:
            raise GraphWorkerError()
        if self._shutdown is None:
            self._shutdown = self.dispatcher.controllers.graph_runs.finish(
                self.dispatcher.capability
            )

    async def _finish_job(self, job_id):
        self._revoke_job(job_id)
        # Cancelling asyncio.to_thread cannot stop its native side effect. Keep
        # the task and drain it after revocation, then resolve host request IDs.
        if self._pending:
            await asyncio.shield(asyncio.gather(*self._pending, return_exceptions=True))
        if self._shutdown is not None:
            self.stops = await asyncio.shield(
                asyncio.to_thread(
                    self.dispatcher.controllers.stop_graph, self._shutdown
                )
            )
            if all(item.settled for item in self.stops):
                self.dispatcher.controllers.graph_runs.settle(
                    self.dispatcher.capability
                )

    async def _request(self, call, cancelled):
        pending = asyncio.create_task(asyncio.to_thread(self.dispatcher.request, call))
        self._pending.add(pending)
        try:
            while True:
                remaining = self._remaining(self.job_id)
                if cancelled.is_set() or remaining is None or remaining <= 0:
                    raise GraphWorkerError()
                try:
                    return await asyncio.wait_for(
                        asyncio.shield(pending), min(0.25, remaining)
                    )
                except asyncio.TimeoutError:
                    continue
        finally:
            # Pending tasks are intentionally retained for exact reconciliation.
            if pending.done():
                self._pending.discard(pending)

    def _completed(self):
        """A worker's terminal message cannot invent native Agent completion."""
        controllers = self.dispatcher.controllers
        for node in self.plan.nodes:
            run_id = controllers.graph_runs.run_for_vertex(
                self.dispatcher.capability, self.plan.graph_digest, node.vertex_id
            )
            slot = controllers.graph_native(self.plan.profile_id, node)
            record = slot.runner.status(run_id)
            self.dispatcher.observe_node(node.vertex_id, record)
            if record.get("status") != "completed":
                raise GraphWorkerError()

    async def _exchange(self, process, job, cancelled):
        bootstrap = BytesIO()
        GraphWorkerChannel.write_message(bootstrap, job.private_payload())
        process.stdin.write(bootstrap.getvalue())
        await process.stdin.drain()
        request_id = 0
        while True:
            remaining = self._remaining(job.job_id)
            if cancelled.is_set() or remaining is None or remaining <= 0:
                raise GraphWorkerError()
            try:
                data = await asyncio.wait_for(
                    process.stdout.readline(), min(0.25, remaining)
                )
            except asyncio.TimeoutError:
                continue
            message = GraphWorkerChannel.read_message(BytesIO(data))
            if "event" in message:
                result = GraphWorkerResult.model_validate(message)
                if result.job_id != job.job_id:
                    raise GraphWorkerError()
                if result.event == "completed":
                    await asyncio.to_thread(self._completed)
                return result
            call = ProviderWorkerCall.model_validate(message)
            if call.request_id != request_id + 1:
                raise GraphWorkerError()
            request_id = call.request_id
            if call.action == "event":
                event = ProviderWorkerEvent.model_validate(call.body)
                vertex = (
                    event.data.get("id")
                    if event.event == "build_start"
                    else event.data.get("build_data", {}).get("id")
                )
                if call.vertex_id not in self.vertices or vertex != call.vertex_id:
                    raise GraphWorkerError()
                if self.on_event is not None:
                    self.on_event(event)
                reply = ProviderWorkerReply(
                    request_id=call.request_id, status=200, payload={}
                )
            else:
                reply = await self._request(call, cancelled)
            output = BytesIO()
            GraphWorkerChannel.write_message(output, reply.model_dump(mode="json"))
            process.stdin.write(output.getvalue())
            await process.stdin.drain()
