"""Real Activity retention from host-derived identities and inert native pages."""

from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from laomedo.agents.activity.models import ActivityPage
from laomedo.agents.connections.models import (
    GraphNodePolicy,
    GraphRunNode,
    GraphRunPlan,
)
from laomedo.integrations.langflow.execution.providers.activity import (
    ProviderGraphActivity,
)


class ProviderGraphActivityTests(unittest.TestCase):
    """A worker does not choose the retained owner, native reader or attempt ID."""

    def test_retention_failure_does_not_escape_into_dispatched_execution(self):
        store, capture = Mock(), Mock()
        capture.bind.side_effect = OSError("fixture unavailable")
        store.finish.side_effect = OSError("fixture unavailable")
        with patch(
            "laomedo.integrations.langflow.execution.providers.activity.ActivityStore",
            return_value=store,
        ):
            bridge = ProviderGraphActivity("fixture", None, None, uuid4())
        bridge.captures["codex"] = capture
        bridge.observe("codex", {"run_id": str(uuid4()), "status": "completed"})
        bridge.observe("codex", {"run_id": str(uuid4()), "status": "completed"})
        capture.bind.assert_called_once()
        capture.refused.set.assert_called_once()
        capture.done.set.assert_called_once()
        store.finish.assert_called_once()

    def test_exact_native_attempt_is_retained_under_the_graph_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            node = GraphRunNode(
                vertex_id="codex",
                provider="codex",
                connection_id=uuid4(),
                generation=1,
                policy=GraphNodePolicy(model="fixture", effort="low", task="Fixture"),
            )
            plan = GraphRunPlan(
                profile_id=uuid4(),
                lease_hash="lease",
                flow_id=uuid4(),
                graph_digest="sha256:" + "a" * 64,
                nodes=(node,),
                deadline=time.monotonic() + 60,
            )
            run, attempt = str(uuid4()), str(uuid4())
            page = ActivityPage(
                run_id=run,
                attempt_id=attempt,
                available=True,
                records=[],
                next_after=0,
                has_more=False,
                closed=True,
                complete=True,
                reason=None,
                status="completed",
            )
            controllers = SimpleNamespace(read_graph_activity=Mock(return_value=page))
            bridge = ProviderGraphActivity(
                Path(directory) / "activity.db", controllers, plan, uuid4()
            )
            bridge.reserve(node)
            bridge.observe(
                node.vertex_id,
                {
                    "run_id": run,
                    "activity_initial_attempt_id": attempt,
                    "status": "completed",
                },
            )
            capture = bridge.captures[node.vertex_id]
            deadline = time.monotonic() + 3
            while True:
                saved = bridge.store.read(
                    str(plan.profile_id),
                    str(plan.flow_id),
                    node.vertex_id,
                    capture.capture.invocation_id,
                )
                if saved["run"]["stream_state"] == "complete":
                    break
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.01)
            controllers.read_graph_activity.assert_called_with(
                plan.profile_id, node, run, attempt, after=0, limit=200
            )
            with self.assertRaises(LookupError):
                bridge.store.read(
                    str(uuid4()),
                    str(plan.flow_id),
                    node.vertex_id,
                    capture.capture.invocation_id,
                )
            controllers.read_graph_activity.return_value = page.model_copy(
                update={"run_id": str(uuid4())}
            )
            with self.assertRaisesRegex(
                ValueError, "activity_runner_identity_mismatch"
            ):
                capture.feed(run, 0)
            pending = node.model_copy(update={"vertex_id": "cancelled-before-poll"})
            bridge.reserve(pending)
            bridge.close()
            sealed = bridge.store.read(
                str(plan.profile_id),
                str(plan.flow_id),
                pending.vertex_id,
                bridge.captures[pending.vertex_id].capture.invocation_id,
            )
            self.assertEqual(sealed["run"]["status"], "failed")
            self.assertEqual(sealed["run"]["reason"], "dispatch_not_bound")
