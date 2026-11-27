"""Host dispatcher tests with real admission/controllers and inert native runs."""

from pathlib import Path
import tempfile
import time
import unittest
from uuid import uuid4

from laomedo.agents.connections.controllers import ProviderControllers
from laomedo.agents.connections.models import (
    ConnectionRecord,
    GraphNodePolicy,
    GraphRunNode,
    GraphRunPlan,
)
from laomedo.agents.connections.service import ProviderConnections
from laomedo.integrations.langflow.execution.providers.dispatcher import (
    ProviderGraphDispatcher,
)
from laomedo.integrations.langflow.execution.providers.models import ProviderWorkerCall
from test_agents.test_connections.test_controllers import FakeNativeAgent


class ProviderDispatcherTests(unittest.TestCase):
    """Worker input cannot select other native identities or add runner authority."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.service = ProviderConnections(root / "accounts")
        self.addCleanup(self.service.close)
        self.profile = uuid4()
        self.record = ConnectionRecord(
            provider="codex",
            connection_id=uuid4(),
            credential_id=uuid4(),
            client_id="fixture",
            subject_hash="fixture",
            generation=1,
            label="Fixture",
        )
        self.service._save(self.profile, [self.record])
        self.controllers = ProviderControllers(
            self.service,
            root / "runs",
            root / "skills",
            root / "source",
            factory=FakeNativeAgent,
        )
        self.addCleanup(self.controllers.close)
        self.plan = GraphRunPlan(
            profile_id=self.profile,
            lease_hash="lease",
            flow_id=uuid4(),
            graph_digest="sha256:" + "a" * 64,
            deadline=time.monotonic() + 60,
            nodes=(
                GraphRunNode(
                    vertex_id="codex",
                    provider="codex",
                    connection_id=self.record.connection_id,
                    generation=1,
                    policy=GraphNodePolicy(
                        model="m", effort="low", task="make fixture edit"
                    ),
                ),
            ),
        )
        self.capability = self.controllers.graph_runs.admit(self.plan)
        self.dispatcher = ProviderGraphDispatcher(
            self.controllers, self.capability, self.plan.graph_digest
        )
        self.body = {
            "request_id": str(uuid4()),
            "task": "make fixture edit",
            "model": "m",
            "effort": "low",
            "skill_refs": [],
        }

    def call(self, path, *, body=None, method="POST", vertex="codex"):
        return self.dispatcher.request(
            ProviderWorkerCall(
                request_id=1,
                action="http",
                vertex_id=vertex,
                method=method,
                path=path,
                body=body,
            )
        )

    def test_native_identity_is_host_issued_and_status_releases_only_safe_fields(self):
        reply = self.call("/v1/runs/async", body=self.body)
        self.assertEqual(reply.status, 202)
        native_id = self.controllers.graph_runs.run_for_vertex(
            self.capability, self.plan.graph_digest, "codex"
        )
        slot = self.controllers.graph_native(self.profile, self.plan.nodes[0])
        native = slot.runner.status(native_id)
        self.assertNotEqual(native["client_request_id"], self.body["request_id"])
        self.assertEqual(reply.payload["client_request_id"], self.body["request_id"])
        native.update(
            task="private task",
            api_token="secret",
            state_path="private",
            grant="secret",
        )
        self.assertNotIn("task", self.dispatcher._status("codex", native))
        self.assertNotIn("api_token", self.dispatcher._status("codex", native))
        self.assertEqual(
            self.call("/v1/requests/" + self.body["request_id"], method="GET").status,
            200,
        )
        self.assertEqual(
            self.call(
                "/v1/requests/" + native["client_request_id"], method="GET"
            ).status,
            409,
        )
        self.assertEqual(
            self.call("/v1/runs/" + str(uuid4()), method="GET").status, 409
        )
        self.assertEqual(
            self.call("/v1/runs/" + native_id + "/cancel", body={}).payload["status"],
            "cancelled",
        )

    def test_authority_fields_and_other_vertices_refuse_before_a_start(self):
        for key, value in (
            ("model", "another-model"),
            ("workspace", "host"),
            ("mcp_servers", [{}]),
            ("task", "changed"),
        ):
            with self.subTest(field=key):
                self.assertEqual(
                    self.call("/v1/runs/async", body={**self.body, key: value}).status,
                    409,
                )
        self.assertEqual(
            self.call("/v1/runs/async", body=self.body, vertex="claude").status, 409
        )
        self.assertEqual(self.call("/v1/runs/async", body=self.body).status, 202)
        self.assertEqual(self.call("/v1/runs/async", body=self.body).status, 409)

    def test_lease_revocation_refuses_every_further_operation(self):
        self.assertEqual(self.call("/v1/runs/async", body=self.body).status, 202)
        self.service.cancel_lease("lease")
        self.assertEqual(
            self.call("/v1/requests/" + self.body["request_id"], method="GET").status,
            409,
        )
        self.assertEqual(
            self.controllers.finish_graph(self.capability)[0].status, "cancelled"
        )
