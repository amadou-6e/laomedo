"""Bounded synchronous broker calls over one job's private process pipe."""

import json
import threading
from uuid import UUID

from pydantic import ValidationError

from laomedo.github.connections.errors import GitHubNodeAuthorizationError
from laomedo.github.connections.models import GitHubWorkerReadRequest
from laomedo.integrations.langflow.execution.errors import GraphWorkerError
from laomedo.integrations.langflow.execution.models import (
    GraphWorkerCall,
    GraphWorkerReply,
)
from laomedo.integrations.langflow.execution.settings import (
    GRAPH_WORKER_MESSAGE_BYTES,
    GRAPH_WORKER_PREFIX,
)


class GraphWorkerChannel:
    """Only one job per process; a channel never discovers ambient credentials."""

    _active = None

    def __init__(self, job, incoming, outgoing):
        """Keep bootstrap and binary process pipes private to this job runtime."""
        self.job = job
        self.incoming = incoming
        self.outgoing = outgoing
        self._request_id = 0
        self._lock = threading.Lock()

    @classmethod
    def install(cls, job, incoming, outgoing):
        """Install once in a fresh worker; never reuse a process for another job."""
        if cls._active is not None:
            raise GraphWorkerError()
        cls._active = cls(job, incoming, outgoing)
        return cls._active

    @classmethod
    def for_graph(cls, graph):
        """Return no channel outside a worker; refuse mismatched jobs inside one."""
        channel = cls._active
        if channel is None:
            return None
        try:
            if UUID(str(graph.run_id)) != channel.job.job_id:
                raise GraphWorkerError()
        except (AttributeError, TypeError, ValueError):
            raise GraphWorkerError() from None
        return channel

    @staticmethod
    def _unique_fields(pairs):
        """Reject repeated JSON keys rather than interpreting ambiguous authority."""
        value = {}
        for key, item in pairs:
            if key in value:
                raise GraphWorkerError()
            value[key] = item
        return value

    @classmethod
    def read_message(cls, incoming):
        """Read one bounded private frame; never echo malformed source bytes."""
        try:
            data = incoming.readline(GRAPH_WORKER_MESSAGE_BYTES + 1)
        except (OSError, ValueError):
            raise GraphWorkerError() from None
        if (
            not isinstance(data, bytes)
            or not data.startswith(GRAPH_WORKER_PREFIX)
            or len(data) > GRAPH_WORKER_MESSAGE_BYTES
            or not data.endswith(b"\n")
        ):
            raise GraphWorkerError()
        try:
            value = json.loads(
                data[len(GRAPH_WORKER_PREFIX) :], object_pairs_hook=cls._unique_fields
            )
            if not isinstance(value, dict):
                raise GraphWorkerError()
            return value
        except (ValueError, UnicodeError, RecursionError):
            raise GraphWorkerError() from None

    @staticmethod
    def write_message(outgoing, value):
        """Write a bounded private frame; callers must not send it to a log sink."""
        try:
            data = (
                GRAPH_WORKER_PREFIX
                + json.dumps(
                    value, ensure_ascii=True, allow_nan=False, separators=(",", ":")
                ).encode("ascii")
                + b"\n"
            )
            if len(data) > GRAPH_WORKER_MESSAGE_BYTES:
                raise GraphWorkerError()
            outgoing.write(data)
            outgoing.flush()
        except (OSError, ValueError, TypeError, RecursionError):
            raise GraphWorkerError() from None

    def inspect(self, vertex_id, labels, state, number=None):
        """Request only this graph vertex's broker-derived repository and target."""
        with self._lock:
            self._request_id += 1
            try:
                call = GraphWorkerCall(
                    request_id=self._request_id,
                    capability=self.job.capability,
                    request=GitHubWorkerReadRequest(
                        job_id=self.job.job_id,
                        vertex_id=vertex_id,
                        labels=labels,
                        state=state,
                        number=number,
                    ),
                )
                self.write_message(self.outgoing, call.private_payload())
                reply = GraphWorkerReply.model_validate(
                    self.read_message(self.incoming)
                )
            except ValidationError:
                raise GraphWorkerError() from None
            if reply.request_id != self._request_id:
                raise GraphWorkerError()
            if reply.code is not None:
                raise GitHubNodeAuthorizationError()
            return reply.payload
