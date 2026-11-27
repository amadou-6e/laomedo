"""Exercise the actual private frame/HTTP adapter without network or models."""

from io import BytesIO
import json
from types import SimpleNamespace
import unittest
from urllib.error import HTTPError
from urllib.request import Request
from uuid import uuid4

from laomedo.integrations.langflow.execution.providers.channel import (
    ProviderWorkerChannel,
    ProviderWorkerHttp,
)
from laomedo.integrations.langflow.execution.providers.models import (
    ProviderNodeRoute,
    ProviderWorkerJob,
)
from laomedo.integrations.langflow.execution.worker.channel import GraphWorkerChannel
from laomedo.integrations.langflow.execution.worker.errors import GraphWorkerError


class ProviderChannelTests(unittest.TestCase):
    """Virtual routing never forwards a host endpoint, credential or other vertex."""

    def channel(self, payload=None, *, status=200, request_id=1):
        incoming, outgoing = BytesIO(), BytesIO()
        GraphWorkerChannel.write_message(
            incoming,
            {
                "version": 2,
                "request_id": request_id,
                "status": status,
                "payload": payload if payload is not None else {"status": "running"},
            },
        )
        incoming.seek(0)
        job = SimpleNamespace(
            providers=(ProviderNodeRoute(vertex_id="codex", port=10000),),
            public_issues=("issue",),
        )
        return ProviderWorkerChannel(job, incoming, outgoing)

    def test_adapter_forwards_only_virtual_vertex_path_and_json_body(self):
        channel = self.channel()
        response = ProviderWorkerHttp(channel).open(
            Request(
                "http://127.0.0.1:10000/v1/runs/async",
                data=b'{"task":"untrusted"}',
                headers={"Authorization": "Bearer should-not-cross"},
            )
        )
        self.assertEqual(json.load(response), {"status": "running"})
        channel.outgoing.seek(0)
        call = GraphWorkerChannel.read_message(channel.outgoing)
        self.assertEqual(
            call,
            {
                "version": 2,
                "request_id": 1,
                "action": "http",
                "vertex_id": "codex",
                "method": "POST",
                "path": "/v1/runs/async",
                "body": {"task": "untrusted"},
            },
        )

    def test_adapter_refuses_arbitrary_destinations_without_sending_a_frame(self):
        for url in (
            "https://127.0.0.1:10000/v1/runs",
            "http://localhost:10000/v1/runs",
            "http://127.0.0.1:10001/v1/runs",
            "http://host.docker.internal/v1/runs",
            "http://127.0.0.1:10000/v1/runs#fragment",
        ):
            with self.subTest(url=url):
                channel = self.channel()
                with self.assertRaises(GraphWorkerError):
                    ProviderWorkerHttp(channel).open(Request(url))
                self.assertEqual(channel.outgoing.getvalue(), b"")

    def test_replies_cannot_change_correlation_or_stage_a_malformed_hash(self):
        with self.assertRaises(GraphWorkerError):
            self.channel(request_id=2).call("issue", "issue")
        for payload in ({"expected_request_hash": "arbitrary"}, {"grant": "secret"}):
            with self.subTest(payload=payload), self.assertRaises(GraphWorkerError):
                self.channel(payload).review("codex", {})

    def test_refusal_preserves_http_error_handling_and_public_issue_pin(self):
        with self.assertRaises(HTTPError) as error:
            ProviderWorkerHttp(self.channel(status=409)).open(
                Request("http://127.0.0.1:10000/v1/runs/async", data=b"{}")
            )
        self.assertEqual(error.exception.code, 409)
        with self.assertRaises(GraphWorkerError):
            self.channel().issue("other-issue", [], "open", 1)

    def test_bootstrap_contains_no_capability_field(self):
        job = ProviderWorkerJob(
            job_id=uuid4(),
            flow_id=uuid4(),
            graph={},
            graph_digest="a" * 64,
            timeout_seconds=60.0,
            providers=(ProviderNodeRoute(vertex_id="codex", port=10000),),
            catalog={
                "entries": (
                    {
                        "component_type": "Codex",
                        "classification": "agent",
                        "code_digest": "b" * 64,
                    },
                )
            },
        )
        self.assertNotIn("capability", job.private_payload())
        self.assertEqual(
            ProviderWorkerJob.model_validate_json(job.model_dump_json()), job
        )

    def test_provider_channel_does_not_inherit_a_github_worker_binding(self):
        from unittest.mock import patch

        with patch.object(GraphWorkerChannel, "_active", self.channel()):
            self.assertIsNone(ProviderWorkerChannel.for_graph(None))
