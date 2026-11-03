from laomedo.agents.activity.models import CaptureIdentity, ActivityInvocation
import tempfile
import unittest
import os
import sqlite3
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

try:
    from fastapi import FastAPI
    from fastapi import Header
    from fastapi import HTTPException
    from fastapi.testclient import TestClient
    from laomedo.agents.activity.routes import install_activity_routes
except ImportError:
    FastAPI = None
from laomedo.agents.activity.store import ActivityStore


class ActivityTests(unittest.TestCase):
    def test_capture_records_visible_name_without_changing_node_identity(self):
        from laomedo.agents.activity.utils import capture_for

        component = SimpleNamespace(
            _user_id="alice",
            graph=SimpleNamespace(run_id="execution", flow_id="flow"),
            _vertex=SimpleNamespace(id="stable-node", display_name="Review PR"),
        )
        with patch.dict(
            os.environ, {"LAOMEDO_AGENT_ACTIVITY_DB": str(self.store.path)}
        ):
            invocation = capture_for(component)
            store, run = invocation.store, invocation.invocation_id
        component._vertex.display_name = "Renamed later"
        summary = store.graph_runs("alice", "flow")[0]
        self.assertEqual(summary["node"], "stable-node")
        self.assertEqual(summary["node_label"], "Review PR")
        self.assertEqual(
            store.read("alice", "flow", "stable-node", run)["run"]["node_label"],
            "Review PR",
        )

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = ActivityStore(Path(self.temp.name) / "activity.db")
        self.run = self.store.start(
            CaptureIdentity.from_values("alice", "flow", "agent")
        )
        if FastAPI is None:
            return
        app = FastAPI()

        def authenticate(authorization: str = Header(default="")):
            if authorization not in {"alice", "bob"}:
                raise HTTPException(401)
            return SimpleNamespace(id=authorization)

        install_activity_routes(app, authenticate, self.store)
        self.client = TestClient(app)
        self.base = "/api/v1/laomedo/agent-activity/flow/agent"

    @unittest.skipIf(FastAPI is None, "optional FastAPI integration is not installed")
    def test_owner_isolation_and_authentication(self):
        self.assertEqual(self.client.get(self.base).status_code, 401)
        self.assertEqual(
            self.client.get(self.base, headers={"Authorization": "bob"}).json()["runs"],
            [],
        )
        self.assertEqual(
            self.client.get(
                self.base + "/" + self.run, headers={"Authorization": "bob"}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(self.base, headers={"Authorization": "alice"}).headers[
                "cache-control"
            ],
            "no-store",
        )

    def test_receipts_persist_replay_and_conflicting_native_ids(self):
        for text in ["first", "first", "conflict"]:
            self.store.append(
                self.run,
                {"type": "item.completed", "item": {"id": "same", "text": text}},
            )
        snapshot = ActivityStore(self.store.path).read(
            "alice", "flow", "agent", self.run, limit=2
        )
        self.assertEqual(snapshot["run"]["event_count"], 3)
        self.assertEqual(snapshot["run"]["action_uniqueness"], "uncertain")
        self.assertEqual([event["sequence"] for event in snapshot["events"]], [1, 2])
        self.assertTrue(snapshot["has_more"])
        tail = self.store.read("alice", "flow", "agent", self.run, after=2)
        self.assertEqual(tail["events"][0]["raw"]["item"]["text"], "conflict")

    def test_unknown_usage_stays_unknown_and_measured_zero_survives(self):
        self.assertIsNone(
            self.store.read("alice", "flow", "agent", self.run)["run"]["usage"]
        )
        self.store.append(
            self.run, {"type": "thread.started", "thread_id": "native-thread"}
        )
        self.store.append(
            self.run,
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 7, "output_tokens": 0},
            },
        )
        run = self.store.read("alice", "flow", "agent", self.run)["run"]
        self.assertEqual(run["usage"]["output_tokens"], 0)
        self.assertEqual(run["native_session"], "native-thread")

    def test_failed_partial_retention_and_closed_trace_refuses_append(self):
        self.store.append(self.run, {"type": "error", "message": "interrupted"})
        self.store.finish(self.run, "cancelled", reason="cancelled")
        run = self.store.read("alice", "flow", "agent", self.run)["run"]
        self.assertEqual(
            (run["status"], run["stream_state"], run["event_count"]),
            ("cancelled", "partial", 1),
        )
        with self.assertRaisesRegex(ValueError, "agent_activity_closed"):
            self.store.append(self.run, {"type": "late"})

    def test_separate_invocations_and_empty_history(self):
        second = self.store.start(CaptureIdentity.from_values("alice", "flow", "agent"))
        self.assertNotEqual(second, self.run)
        self.assertEqual(len(self.store.runs("alice", "flow", "agent")), 2)
        self.assertEqual(self.store.runs("alice", "other-flow", "agent"), [])

    @unittest.skipIf(FastAPI is None, "optional FastAPI integration is not installed")
    def test_pagination_validation_and_no_html_transformation(self):
        self.store.append(
            self.run,
            {"type": "item.completed", "item": {"text": "<script>bad()</script>"}},
        )
        response = self.client.get(
            self.base + "/" + self.run, headers={"Authorization": "alice"}
        )
        self.assertEqual(
            response.json()["events"][0]["raw"]["item"]["text"],
            "<script>bad()</script>",
        )
        for query in ("?after=-1", "?limit=201", "?limit=0"):
            self.assertEqual(
                self.client.get(
                    self.base + "/" + self.run + query,
                    headers={"Authorization": "alice"},
                ).status_code,
                422,
            )

    def test_reservation_requires_durable_identity(self):
        with self.assertRaisesRegex(ValueError, "agent_activity_identity_required"):
            self.store.start(CaptureIdentity.from_values("", "flow", "node"))

    @unittest.skipIf(FastAPI is None, "optional FastAPI integration is not installed")
    def test_graph_routes_preserve_owner_scope_and_node_identity(self):
        base = "/api/v1/laomedo/agent-executions/flow"
        self.assertEqual(self.client.get(base).status_code, 401)
        self.assertEqual(
            self.client.get(base, headers={"Authorization": "bob"}).json()["runs"], []
        )
        self.assertEqual(
            self.client.get(
                base + "/agent/" + self.run, headers={"Authorization": "bob"}
            ).status_code,
            404,
        )
        response = self.client.get(
            base + "/agent/" + self.run, headers={"Authorization": "alice"}
        )
        self.assertEqual(response.json()["run"]["node"], "agent")
        self.assertEqual(response.headers["cache-control"], "no-store")

    @unittest.skipIf(FastAPI is None, "optional FastAPI integration is not installed")
    def test_truncated_projection_does_not_claim_full_usage_or_cost(self):
        event = {
            "sequence": 1,
            "received_at": "2026-10-15T00:00:00Z",
            "raw": {
                "method": "thread/tokenUsage/updated",
                "params": {
                    "threadId": "thread",
                    "tokenUsage": {
                        "total": {
                            "inputTokens": 100,
                            "cachedInputTokens": 0,
                            "outputTokens": 1,
                        }
                    },
                },
            },
        }

        def page(*args):
            after = args[4]
            return {
                "run": {"native_session": "thread", "model": "gpt-6-luna"},
                "events": [event] * 200,
                "next_after": after + 200,
                "has_more": True,
            }

        with patch.object(self.store, "read", side_effect=page):
            value = self.client.get(
                "/api/v1/laomedo/agent-executions/flow/agent/" + self.run,
                headers={"Authorization": "alice"},
            ).json()
        self.assertTrue(value["truncated"])
        self.assertIsNone(value["projection"]["usage"])
        self.assertIsNone(value["projection"]["cost"]["amount"])
        self.assertEqual(value["projection"]["usage_points"], [])
        self.assertEqual(value["projection"]["usage_by_thread"], {})
        self.assertTrue(
            all(
                turn["usage"] is None and turn["cost"]["amount"] is None
                for turn in value["projection"]["turns"]
            )
        )

    def test_read_only_store_uses_existing_database_without_schema_writes(self):
        original = self.store.path.read_bytes()
        reader = ActivityStore(self.store.path, read_only=True)
        self.assertEqual(len(reader.runs("alice", "flow", "agent")), 1)
        self.assertEqual(self.store.path.read_bytes(), original)
        with self.assertRaises(sqlite3.OperationalError):
            reader.start(CaptureIdentity.from_values("alice", "flow", "agent"))

    @unittest.skipIf(FastAPI is None, "optional FastAPI integration is not installed")
    def test_get_does_not_create_uninitialized_database_or_directory(self):
        missing = Path(self.temp.name) / "missing" / "activity.db"
        app = FastAPI()
        install_activity_routes(app, lambda: SimpleNamespace(id="alice"))
        with patch.dict(os.environ, {"LAOMEDO_AGENT_ACTIVITY_DB": str(missing)}):
            response = TestClient(app).get(self.base)
        self.assertEqual(response.status_code, 503)
        self.assertFalse(missing.parent.exists())
