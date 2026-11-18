"""Supervise one credential-free container and its private broker pipe."""

import asyncio
from contextlib import suppress
from io import BytesIO
import secrets
import threading
from uuid import uuid4

from pydantic import SecretStr

from laomedo.host.leases.models import ContainerIdentity
from laomedo.host.leases.settings import LABEL_RUN, LABEL_TOKEN
from laomedo.integrations.langflow.execution.base import BaseDockerRuntime
from laomedo.integrations.langflow.execution.worker.channel import GraphWorkerChannel
from laomedo.integrations.langflow.execution.worker.errors import GraphWorkerError
from laomedo.integrations.langflow.execution.worker.models import (
    GraphWorkerCall,
    GraphWorkerReply,
    GraphWorkerResult,
)
from laomedo.integrations.langflow.execution.worker.settings import (
    GRAPH_WORKER_MESSAGE_BYTES,
    GRAPH_WORKER_MODULE,
)


class DockerGraphWorker(BaseDockerRuntime):
    """One fresh sandbox per admitted job; credentials stay in the calling broker."""

    runtime_error = GraphWorkerError

    def __init__(self, settings, authority, access):
        """Use explicit deployment settings and broker-owned authority/read dispatch."""
        super().__init__(settings)
        self.authority = authority
        self.access = access
        self._jobs = {}

    def _verify_sandbox(self, entry):
        """Verify job confinement and refuse every image/host state mount."""
        self._verify_limits(entry)
        if (
            entry["Config"].get("Volumes")
            or entry.get("Mounts")
            or entry["HostConfig"].get("Binds")
        ):
            raise GraphWorkerError()

    def cancel(self, job_id, owner_id):
        """Revoke a trusted caller's own job before waking cancellation cleanup."""
        run = self.authority.run_for_job(job_id)
        event = self._jobs.get(job_id)
        if run is None or run.scope.owner_id != owner_id or event is None:
            return False
        self.authority.revoke_worker(job_id)
        event.set()
        return True

    async def _read(self, call, cancelled):
        """Interrupt in-flight reads promptly when authority expires or is revoked."""
        pending = asyncio.create_task(
            self.access.inspect(call.capability, call.request)
        )
        try:
            while True:
                remaining = self.authority.worker_remaining(call.request.job_id)
                if cancelled.is_set() or remaining is None:
                    raise GraphWorkerError()
                if remaining <= 0:
                    raise GraphWorkerError()
                try:
                    return await asyncio.wait_for(
                        asyncio.shield(pending), min(0.25, remaining)
                    )
                except asyncio.TimeoutError:
                    continue
        finally:
            if not pending.done():
                pending.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await pending

    async def _exchange(self, process, job, cancelled):
        """Dispatch serial read-only calls and accept one correlated terminal outcome."""
        bootstrap = BytesIO()
        GraphWorkerChannel.write_message(bootstrap, job.private_payload())
        process.stdin.write(bootstrap.getvalue())
        await process.stdin.drain()
        request_id = 0
        while True:
            remaining = self.authority.worker_remaining(job.job_id)
            if cancelled.is_set() or remaining is None:
                raise GraphWorkerError()
            if remaining <= 0:
                raise GraphWorkerError()
            try:
                data = await asyncio.wait_for(
                    process.stdout.readline(), timeout=min(0.25, remaining)
                )
            except asyncio.TimeoutError:
                continue
            message = GraphWorkerChannel.read_message(BytesIO(data))
            if "event" in message:
                result = GraphWorkerResult.model_validate(message)
                if result.job_id != job.job_id:
                    raise GraphWorkerError()
                return result
            call = GraphWorkerCall.model_validate(message)
            if call.request.job_id != job.job_id or call.request_id != request_id + 1:
                raise GraphWorkerError()
            request_id = call.request_id
            try:
                payload = await self._read(call, cancelled)
                reply = GraphWorkerReply(request_id=request_id, payload=payload)
            except Exception:
                reply = GraphWorkerReply(
                    request_id=request_id, code="github_node_authorization_unavailable"
                )
            output = BytesIO()
            GraphWorkerChannel.write_message(output, reply.model_dump(mode="json"))
            process.stdin.write(output.getvalue())
            await process.stdin.drain()

    async def run(self, job):
        """Run an admitted job with independent lease cleanup and no host-state mounts.

        Callers must have already authenticated browser admission and pinned the
        graph/catalog. This internal method is never a worker-facing endpoint.
        The broker owns job identity, timeout, authority and output release.
        """
        if job.job_id in self._jobs:
            raise GraphWorkerError()
        run = self.authority.run_for_job(job.job_id)
        if (
            run is None
            or run.flow_id != job.flow_id
            or run.graph_digest != job.graph_digest
        ):
            raise GraphWorkerError()
        self.authority.validate_job_graph(job.job_id, job.graph)
        first_vertex = run.nodes[0].selection.vertex_id
        cancelled = threading.Event()
        self._jobs[job.job_id] = cancelled
        identity = ContainerIdentity(
            name="laomedo-graph-" + uuid4().hex,
            run_id=str(job.job_id),
            token=SecretStr(secrets.token_hex(16)),
        )
        environment = self._environment()
        lease = process = None
        try:
            await self.authority.revalidate_worker(
                job.capability, job_id=job.job_id, vertex_id=first_vertex
            )
            await self._local_context(environment)
            registration = self._start_lease(identity, cancelled)
            try:
                lease = await asyncio.shield(registration)
            except asyncio.CancelledError:
                # Cancellation cannot stop a registration thread; recover its
                # handle so finally can stop the resulting heartbeat.
                lease = await asyncio.shield(registration)
                raise
            created = await self._control(
                [
                    "create",
                    *self._hardening_arguments(),
                    "--interactive",
                    "--name",
                    identity.name,
                    "--label",
                    LABEL_RUN + "=" + identity.run_id,
                    "--label",
                    LABEL_TOKEN + "=" + identity.token.get_secret_value(),
                    "--entrypoint",
                    "python",
                    self.settings.image_id,
                    "-m",
                    GRAPH_WORKER_MODULE,
                ],
                environment,
            )
            if created.returncode:
                raise GraphWorkerError()
            entry = await self._inspect(identity, environment)
            self._verify_sandbox(entry)
            process = await asyncio.create_subprocess_exec(
                "docker",
                "start",
                "--attach",
                "--interactive",
                entry["Id"],
                env=environment,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                limit=GRAPH_WORKER_MESSAGE_BYTES,
            )
            remaining = self.authority.worker_remaining(job.job_id)
            if remaining is None or remaining <= 0:
                raise GraphWorkerError()
            job = job.model_copy(
                update={"timeout_seconds": min(job.timeout_seconds, remaining)}
            )
            result = await asyncio.wait_for(
                self._exchange(process, job, cancelled), timeout=remaining
            )
            await asyncio.wait_for(
                process.wait(), timeout=self.settings.control_timeout_seconds
            )
            if result.event == "completed" and process.returncode != 0:
                raise GraphWorkerError()
            await self.authority.revalidate_worker(
                job.capability, job_id=job.job_id, vertex_id=first_vertex
            )
            return result
        finally:
            self.authority.finish_job(job.job_id)
            self._jobs.pop(job.job_id, None)
            try:
                await self._remove(identity, environment)
            finally:
                if process is not None and process.returncode is None:
                    process.kill()
                    await process.wait()
                if lease is not None:
                    await asyncio.to_thread(lease.finish)
