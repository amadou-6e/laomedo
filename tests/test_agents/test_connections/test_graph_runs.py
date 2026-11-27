"""Host authority invariants; these checks do not establish worker isolation."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import time
import unittest
from uuid import uuid4

from laomedo.agents.connections.errors import ProviderConnectionError
from laomedo.agents.connections.graph_runs import ProviderGraphRuns
from laomedo.agents.connections.models import ConnectionRecord
from laomedo.agents.connections.models import GraphRunNode
from laomedo.agents.connections.models import GraphRunPlan
from laomedo.agents.connections.service import ProviderConnections


class ProviderGraphRunTests(unittest.TestCase):
    """A worker cannot select a foreign owner, epoch, invocation or source run."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.service = ProviderConnections(Path(temporary.name) / "connections")
        self.addCleanup(self.service.close)
        self.owner = uuid4()
        self.records = tuple(
            ConnectionRecord(
                provider=provider,
                connection_id=uuid4(),
                credential_id=uuid4(),
                client_id="fixture",
                subject_hash=str(uuid4()),
                generation=1,
                label="Fixture",
            )
            for provider in ("codex", "claude")
        )
        self.service._save(self.owner, list(self.records))
        self.authority = ProviderGraphRuns(self.service)
        self.plan = GraphRunPlan(
            profile_id=self.owner,
            lease_hash="fixture-browser-lease",
            flow_id=uuid4(),
            graph_digest="sha256:" + "a" * 64,
            nodes=tuple(
                GraphRunNode(
                    vertex_id=record.provider,
                    provider=record.provider,
                    connection_id=record.connection_id,
                    generation=record.generation,
                    review_source="codex" if record.provider == "claude" else None,
                )
                for record in self.records
            ),
            deadline=time.monotonic() + 60,
        )

    def test_review_source_comes_from_this_invocations_host_receipt(self):
        first = self.authority.admit(self.plan)
        second = self.authority.admit(self.plan)
        with self.assertRaises(ProviderConnectionError):
            self.authority.review(first, self.plan.graph_digest, "claude")
        run_id = str(uuid4())
        self.authority.begin_node(first, self.plan.graph_digest, "codex")
        self.authority.bind_run(first, self.plan.graph_digest, "codex", run_id)
        self.assertEqual(
            self.authority.review(first, self.plan.graph_digest, "claude").source_run,
            run_id,
        )
        with self.assertRaises(ProviderConnectionError):
            self.authority.review(second, self.plan.graph_digest, "claude")
        with self.assertRaises(ProviderConnectionError):
            self.authority.bind_run(
                first, self.plan.graph_digest, "codex", str(uuid4())
            )

    def test_foreign_graph_vertex_and_capability_do_not_authorize(self):
        capability = self.authority.admit(self.plan)
        self.assertEqual(
            self.authority.resolve(capability, self.plan.graph_digest, "codex"),
            self.plan.nodes[0],
        )
        for token, digest, vertex in (
            ("b" * 64, self.plan.graph_digest, "codex"),
            (str(self.plan.flow_id), self.plan.graph_digest, "codex"),
            (capability, "sha256:" + "b" * 64, "codex"),
            (capability, "different\u00e9", "codex"),
            (capability, self.plan.graph_digest, "foreign-node"),
        ):
            with self.subTest(vertex=vertex, digest=digest):
                with self.assertRaises(ProviderConnectionError):
                    self.authority.resolve(token, digest, vertex)

    def test_owner_generation_and_logout_are_checked_at_every_access(self):
        with self.assertRaises(ProviderConnectionError):
            self.authority.admit(self.plan.model_copy(update={"profile_id": uuid4()}))
        capability = self.authority.admit(self.plan)
        self.service._save(
            self.owner,
            [self.records[0].model_copy(update={"generation": 2}), self.records[1]],
        )
        with self.assertRaises(ProviderConnectionError):
            self.authority.resolve(capability, self.plan.graph_digest, "codex")
        with self.assertRaises(ProviderConnectionError):
            self.authority.review(capability, self.plan.graph_digest, "claude")
        self.service._save(self.owner, list(self.records))
        self.service.cancel_lease(self.plan.lease_hash)
        with self.assertRaises(ProviderConnectionError):
            self.authority.resolve(capability, self.plan.graph_digest, "claude")

    def test_finished_worker_cannot_replay_or_rebind(self):
        capability = self.authority.admit(self.plan)
        self.authority.begin_node(capability, self.plan.graph_digest, "codex")
        self.authority.bind_run(
            capability, self.plan.graph_digest, "codex", str(uuid4())
        )
        self.authority.finish(capability)
        with self.assertRaises(ProviderConnectionError):
            self.authority.review(capability, self.plan.graph_digest, "claude")
        with self.assertRaises(ProviderConnectionError):
            self.authority.bind_run(
                capability, self.plan.graph_digest, "codex", str(uuid4())
            )

    def test_start_reservation_prevents_replay_before_acknowledgement(self):
        capability = self.authority.admit(self.plan)
        with self.assertRaises(ProviderConnectionError):
            self.authority.bind_run(
                capability, self.plan.graph_digest, "codex", str(uuid4())
            )
        with self.assertRaises(ProviderConnectionError):
            self.authority.begin_node(capability, self.plan.graph_digest, "claude")
        self.authority.begin_node(capability, self.plan.graph_digest, "codex")
        with self.assertRaises(ProviderConnectionError):
            self.authority.begin_node(capability, self.plan.graph_digest, "codex")

    def test_expired_or_ambiguous_plans_never_admit(self):
        for update in (
            {"deadline": time.monotonic() - 1},
            {"deadline": float("inf")},
            {"nodes": self.plan.nodes + (self.plan.nodes[0],)},
            {"nodes": (self.plan.nodes[1],)},
        ):
            with self.subTest(update=tuple(update)):
                with self.assertRaises(ProviderConnectionError):
                    self.authority.admit(self.plan.model_copy(update=update))

    def test_concurrent_acknowledgements_cannot_replace_a_source(self):
        capability = self.authority.admit(self.plan)
        self.authority.begin_node(capability, self.plan.graph_digest, "codex")
        candidates = (str(uuid4()), str(uuid4()))
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    self.authority.bind_run,
                    capability,
                    self.plan.graph_digest,
                    "codex",
                    run_id,
                )
                for run_id in candidates
            ]
        self.assertEqual(sum(future.exception() is None for future in futures), 1)
        self.assertIn(
            self.authority.review(
                capability, self.plan.graph_digest, "claude"
            ).source_run,
            candidates,
        )
