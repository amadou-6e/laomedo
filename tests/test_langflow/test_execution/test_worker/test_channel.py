"""Private framing, job identity and capability projection without a provider."""

from io import BytesIO
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from laomedo.github.node_runs.errors import GitHubNodeAuthorizationError
from laomedo.github.node_runs.authority import GitHubRunAuthority
from laomedo.integrations.langflow.graph_admission.catalog import GitHubGraphCatalog
from laomedo.integrations.langflow.execution.worker.channel import GraphWorkerChannel
from laomedo.integrations.langflow.execution.worker.errors import GraphWorkerError
from laomedo.integrations.langflow.execution.worker.models import (
    GraphWorkerCall,
    GraphWorkerJob,
)
from laomedo.integrations.langflow.execution.worker.settings import GRAPH_WORKER_PREFIX


class GraphWorkerChannelTests(unittest.TestCase):
    """A channel carries one job only, never ambient or reusable GitHub credentials."""

    def setUp(self):
        active = patch.object(GraphWorkerChannel, "_active", None)
        active.start()
        self.addCleanup(active.stop)
        graph = {"nodes": [], "edges": []}
        catalog = GitHubGraphCatalog.capture(
            {
                "Laomedo": {
                    "LaomedoGitHubPR": {
                        "template": {"code": {"value": "synthetic code"}}
                    }
                }
            }
        )
        self.job = GraphWorkerJob(
            job_id=uuid4(),
            flow_id=uuid4(),
            graph=graph,
            graph_digest=GitHubRunAuthority.digest_graph(graph),
            catalog=catalog.snapshot,
            capability="w" * 43,
            timeout_seconds=60.0,
        )
        self.incoming = BytesIO()
        self.outgoing = BytesIO()

    def reply(self, value):
        stream = BytesIO()
        GraphWorkerChannel.write_message(stream, value)
        stream.seek(0)
        return stream

    def test_inspect_sends_job_vertex_and_filters_only_on_private_pipe(self):
        incoming = self.reply({"request_id": 1, "payload": {"private": "result"}})
        channel = GraphWorkerChannel(self.job, incoming, self.outgoing)
        self.assertEqual(
            channel.inspect("pr-1", ["bug"], "open"), {"private": "result"}
        )
        self.outgoing.seek(0)
        call = GraphWorkerCall.model_validate(
            GraphWorkerChannel.read_message(self.outgoing)
        )
        self.assertEqual(call.request.job_id, self.job.job_id)
        self.assertEqual(call.request.vertex_id, "pr-1")
        self.assertEqual(call.request.labels, ["bug"])
        self.assertEqual(call.capability, self.job.capability)
        self.assertNotIn("w" * 43, call.model_dump_json())
        self.assertNotIn("w" * 43, self.job.model_dump_json())
        self.assertNotIn("w" * 43, repr(self.job))

    def test_worker_install_is_one_job_only_and_graph_cannot_change_identity(self):
        self.assertIsNone(GraphWorkerChannel.for_graph(None))
        channel = GraphWorkerChannel.install(self.job, self.incoming, self.outgoing)
        self.assertIs(
            GraphWorkerChannel.for_graph(SimpleNamespace(run_id=self.job.job_id)),
            channel,
        )
        with self.assertRaises(GraphWorkerError):
            GraphWorkerChannel.install(self.job, self.incoming, self.outgoing)
        for run_id in (uuid4(), "malformed", None):
            with self.assertRaises(GraphWorkerError):
                GraphWorkerChannel.for_graph(SimpleNamespace(run_id=run_id))

    def test_mismatched_reply_or_ambiguous_result_is_not_delivered_to_graph(self):
        for value in (
            {"request_id": 2, "payload": {"wrong": "reply"}},
            {
                "request_id": 1,
                "payload": {},
                "code": "github_node_authorization_unavailable",
            },
            {"request_id": 1},
        ):
            channel = GraphWorkerChannel(self.job, self.reply(value), BytesIO())
            with self.assertRaises(GraphWorkerError):
                channel.inspect("pr-1", [], "open")

    def test_broker_refusal_never_becomes_success_or_credential_fallback(self):
        channel = GraphWorkerChannel(
            self.job,
            self.reply(
                {"request_id": 1, "code": "github_node_authorization_unavailable"}
            ),
            BytesIO(),
        )
        with self.assertRaises(GitHubNodeAuthorizationError):
            channel.inspect("pr-1", [], "open")

    def test_runtime_failure_does_not_claim_authorization_failed_before_dispatch(self):
        channel = GraphWorkerChannel(
            self.job,
            self.reply({"request_id": 1, "code": "github_graph_runtime_unavailable"}),
            BytesIO(),
        )
        with self.assertRaises(GraphWorkerError):
            channel.inspect("pr-1", [], "open")

    def test_malformed_and_duplicate_json_is_refused_without_echoing_private_text(self):
        for data in (
            b"not a private frame\n",
            GRAPH_WORKER_PREFIX + b"[]\n",
            GRAPH_WORKER_PREFIX + b'{"payload":"private text","payload":{}}\n',
            GRAPH_WORKER_PREFIX + json.dumps({"payload": "private text"}).encode(),
        ):
            with self.assertRaises(GraphWorkerError) as caught:
                GraphWorkerChannel.read_message(BytesIO(data))
            self.assertNotIn("private text", str(caught.exception))

    def test_closed_pipe_is_a_fixed_failure(self):
        channel = GraphWorkerChannel(self.job, BytesIO(), self.outgoing)
        with self.assertRaises(GraphWorkerError):
            channel.inspect("pr-1", [], "open")
        closed = BytesIO()
        closed.close()
        with self.assertRaises(GraphWorkerError):
            GraphWorkerChannel.read_message(closed)
