"""Virtual per-vertex HTTP over an isolated job's private pipe, with no network."""

from io import BytesIO
import json
import re
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request

from laomedo.integrations.langflow.execution.worker.channel import GraphWorkerChannel
from laomedo.integrations.langflow.execution.worker.errors import GraphWorkerError
from laomedo.integrations.langflow.execution.providers.models import (
    ProviderWorkerCall,
    ProviderWorkerReply,
)


class ProviderWorkerChannel(GraphWorkerChannel):
    """Use a host-bound pipe; no runner or admission capability enters the worker."""

    _active = None

    @classmethod
    def install(cls, job, incoming, outgoing):
        channel = super().install(job, incoming, outgoing)
        routes = job.providers
        if len({route.vertex_id for route in routes}) != len(routes) or len(
            {route.port for route in routes}
        ) != len(routes):
            raise GraphWorkerError()
        from laomedo.agents.interface.langflow.component import AgentComponent

        AgentComponent.install_worker_transport(ProviderWorkerHttp(channel))
        return channel

    def endpoint(self, vertex_id):
        for route in self.job.providers:
            if route.vertex_id == vertex_id:
                return "http://127.0.0.1:" + str(route.port)
        raise GraphWorkerError()

    def call(self, action, vertex_id, *, method="POST", path="", body=None):
        with self._lock:
            self._request_id += 1
            request = ProviderWorkerCall(
                request_id=self._request_id,
                action=action,
                vertex_id=vertex_id,
                method=method,
                path=path,
                body=body,
            )
            self.write_message(self.outgoing, request.model_dump(mode="json"))
            reply = ProviderWorkerReply.model_validate_json(
                json.dumps(self.read_message(self.incoming), allow_nan=False)
            )
            if reply.request_id != self._request_id:
                raise GraphWorkerError()
            return reply

    def review(self, vertex_id, body):
        reply = self.call("review", vertex_id, body=body)
        if (
            reply.status != 200
            or set(reply.payload) != {"expected_request_hash"}
            or not isinstance(reply.payload["expected_request_hash"], str)
            or re.fullmatch(
                r"sha256:[0-9a-f]{64}", reply.payload["expected_request_hash"]
            )
            is None
        ):
            raise GraphWorkerError()
        return reply.payload["expected_request_hash"]

    def issue(self, vertex_id, labels, state, number):
        if vertex_id not in self.job.public_issues:
            raise GraphWorkerError()
        reply = self.call(
            "issue",
            vertex_id,
            body={"number": number, "labels": labels, "state": state},
        )
        if reply.status != 200:
            raise GraphWorkerError()
        return reply.payload


class ProviderWorkerHttp:
    """Translate virtual addresses to pipe calls; never forward a URL or header."""

    def __init__(self, channel):
        self.channel = channel

    def open(self, request, timeout=None):
        if not isinstance(request, Request):
            raise GraphWorkerError()
        parsed = urlsplit(request.full_url)
        route = next(
            (
                route
                for route in self.channel.job.providers
                if parsed.netloc == "127.0.0.1:" + str(route.port)
            ),
            None,
        )
        if parsed.scheme != "http" or route is None or parsed.fragment:
            raise GraphWorkerError()
        body = None
        if request.data is not None:
            body = json.loads(
                request.data, object_pairs_hook=self.channel._unique_fields
            )
            if not isinstance(body, dict):
                raise GraphWorkerError()
        reply = self.channel.call(
            "http",
            route.vertex_id,
            method=request.get_method(),
            path=parsed.path + ("?" + parsed.query if parsed.query else ""),
            body=body,
        )
        response = ProviderWorkerResponse(reply.status, reply.payload)
        if reply.status >= 400:
            raise HTTPError(
                request.full_url, reply.status, "Graph operation refused", {}, response
            )
        return response


class ProviderWorkerResponse(BytesIO):
    """Preserve the existing urllib JSON consumer without any socket or credential."""

    def __init__(self, status, payload):
        super().__init__(json.dumps(payload, allow_nan=False).encode("utf-8"))
        self.status = status

    def getcode(self):
        return self.status
