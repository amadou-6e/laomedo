from laomedo.agents.activity.models import ActivityPage
from laomedo.agents.activity.models import ActivityRecord
from laomedo.agents.activity.models import ActivityProjection
from laomedo.agents.activity.models import MessageActivity
from datetime import datetime, timezone

"""Internal tests only; real graph acceptance is recorded separately."""

from laomedo.agents.activity.models import CaptureIdentity
from laomedo.agents.activity.models import ActivityInvocation
import json
from pathlib import Path
import tempfile
import unittest
import threading
from concurrent.futures import ThreadPoolExecutor

from laomedo.agents.activity.store import ActivityStore
from laomedo.agents.agents.codex.activity.projection import project
from laomedo.agents.agents.codex.activity.cost import estimate
from laomedo.agents.activity.runner.feed import notification
from laomedo.agents.activity.runner.feed import read_feed


class GraphActivityTests(unittest.TestCase):
    def test_native_turn_usage_uses_cumulative_boundary_deltas_and_ignores_last(self):
        def receipt(raw):
            return {"received_at": "2026-10-24T18:00:00Z", "raw": raw}

        events = [
            {
                "method": "capture/usageBaseline",
                "threads": {
                    "root": {
                        "total": {
                            "inputTokens": 100,
                            "cachedInputTokens": 20,
                            "outputTokens": 10,
                        }
                    }
                },
            },
            {"method": "turn/started", "params": {"threadId": "root", "turnId": "t1"}},
        ]
        for value in (120, 145, 145):
            events.append(
                {
                    "method": "thread/tokenUsage/updated",
                    "params": {
                        "threadId": "root",
                        "turnId": "t1",
                        "tokenUsage": {
                            "total": {
                                "inputTokens": value,
                                "cachedInputTokens": 25,
                                "outputTokens": 15,
                            },
                            "last": {"inputTokens": 3},
                        },
                    },
                }
            )
        events.extend(
            [
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": "root",
                        "turnId": "t1",
                        "turn": {"status": "completed"},
                    },
                },
                {
                    "method": "turn/started",
                    "params": {"threadId": "root", "turnId": "t2"},
                },
                {
                    "method": "thread/tokenUsage/updated",
                    "params": {
                        "threadId": "root",
                        "turnId": "t2",
                        "tokenUsage": {
                            "total": {
                                "inputTokens": 155,
                                "cachedInputTokens": 25,
                                "outputTokens": 17,
                            },
                            "last": {"inputTokens": 2},
                        },
                    },
                },
            ]
        )
        result = project(
            [receipt(raw) for raw in events], root_thread="root"
        ).to_payload()
        self.assertEqual(
            [turn["usage"]["inputTokens"] for turn in result["turns"]], [45, 10]
        )
        self.assertEqual(
            [point["turn_usage"]["inputTokens"] for point in result["usage_points"]],
            [20, 45, 45, 10],
        )
        self.assertEqual(result["usage"]["inputTokens"], 55)
        missing = project(
            [
                receipt(
                    {
                        "method": "turn/started",
                        "params": {"threadId": "root", "turnId": "t"},
                    }
                ),
                receipt(
                    {
                        "method": "thread/tokenUsage/updated",
                        "params": {
                            "threadId": "root",
                            "turnId": "t",
                            "tokenUsage": {
                                "total": {"inputTokens": 100},
                                "last": {"inputTokens": 7},
                            },
                        },
                    }
                ),
            ],
            root_thread="root",
        ).to_payload()
        self.assertIsNone(missing["turns"][0]["usage"])
        self.assertIsNone(missing["usage_points"][0]["turn_usage"])

    def test_turn_usage_stays_unknown_after_counter_regression(self):
        raw = [
            {
                "method": "capture/usageBaseline",
                "threads": {"root": {"total": {"inputTokens": 10}}},
            },
            {"method": "turn/started", "params": {"threadId": "root", "turnId": "t"}},
        ]
        raw.extend(
            {
                "method": "thread/tokenUsage/updated",
                "params": {
                    "threadId": "root",
                    "turnId": "t",
                    "tokenUsage": {"total": {"inputTokens": value}},
                },
            }
            for value in (20, 5, 30)
        )
        result = project(
            [{"raw": event, "received_at": "2026-10-24T18:00:00Z"} for event in raw],
            root_thread="root",
        ).to_payload()
        self.assertIsNone(result["turns"][0]["usage"])
        self.assertIsNone(result["turns"][0]["cost"]["amount"])

    def test_concurrent_first_captures_serialize_schema_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "activity.db"

            def start(index):
                return ActivityStore(path).start(
                    CaptureIdentity.from_values(
                        "alice", "flow", f"node-{index}", execution="graph"
                    )
                )

            with ThreadPoolExecutor(max_workers=8) as pool:
                runs = list(pool.map(start, range(8)))
            self.assertEqual(len(set(runs)), 8)
            self.assertEqual(
                len(ActivityStore(path, read_only=True).graph_runs("alice", "flow")), 8
            )

    def test_read_only_missing_store_does_not_create_anything(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "absent/activity.db"
            with self.assertRaises(LookupError):
                ActivityStore(path, read_only=True)
            self.assertFalse(path.parent.exists())

    def test_execution_owner_scope_and_retry_deduplication(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ActivityStore(Path(directory) / "activity.db")
            first = store.start(
                CaptureIdentity.from_values("alice", "flow", "agent", execution="first")
            )
            store.start(
                CaptureIdentity.from_values(
                    "alice", "flow", "agent", execution="second"
                )
            )
            store.start(
                CaptureIdentity.from_values("bob", "flow", "agent", execution="first")
            )
            event = {"method": "item/completed", "params": {"item": {"id": "same"}}}
            for cursor in (1, 1, 2):
                store.append(first, event, source="native", cursor=cursor)
            runs = store.graph_runs("alice", "flow", "first")
            self.assertEqual([run["id"] for run in runs], [first])
            self.assertEqual(runs[0]["event_count"], 2)
            readonly = ActivityStore(store.path, read_only=True)
            with self.assertRaises(Exception):
                readonly.start(CaptureIdentity.from_values("alice", "flow", "agent"))

    def test_feed_excludes_account_and_rpc_responses(self):
        for event in (
            {"id": 1, "result": {"token": "private"}},
            {"method": "account/updated"},
            {"method": "models/list"},
        ):
            self.assertFalse(notification(event))
        self.assertTrue(notification({"method": "item/completed"}))

    def test_incomplete_feed_write_is_not_consumed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            path.write_bytes(b'{"event":{}}\n{"event":')
            self.assertEqual(read_feed(path)["next_after"], 1)
            with path.open("ab") as output:
                output.write(b"{}}\n")
            self.assertEqual(read_feed(path, after=1)["events"][0]["cursor"], 2)

    def test_counter_regression_is_unknown_even_after_positive_snapshot(self):
        events = [
            {
                "raw": {
                    "method": "thread/tokenUsage/updated",
                    "params": {
                        "threadId": "thread",
                        "tokenUsage": {
                            "total": {
                                "inputTokens": value,
                                "cachedInputTokens": 0,
                                "outputTokens": 1,
                            }
                        },
                    },
                },
                "received_at": "2026-10-15T00:00:00Z",
            }
            for value in [100, 50, 120]
        ]
        result = project(events, root_thread="thread", model="gpt-6-luna").to_payload()
        self.assertIsNone(result["usage"])
        self.assertIsNone(result["cost"]["amount"])

    def test_resume_deltas_and_repeated_cumulative_updates(self):
        events = [
            {
                "method": "capture/usageBaseline",
                "threads": {
                    "thread": {
                        "total": {
                            "inputTokens": 100,
                            "cachedInputTokens": 20,
                            "outputTokens": 10,
                        }
                    }
                },
            }
        ]
        for inputs, cached, outputs in [(130, 30, 15), (130, 30, 15), (150, 40, 20)]:
            events.append(
                {
                    "method": "thread/tokenUsage/updated",
                    "params": {
                        "threadId": "thread",
                        "turnId": "turn",
                        "tokenUsage": {
                            "total": {
                                "inputTokens": inputs,
                                "cachedInputTokens": cached,
                                "outputTokens": outputs,
                            }
                        },
                    },
                }
            )
        result = project(
            [{"raw": raw, "received_at": "2026-10-15T00:00:00Z"} for raw in events],
            root_thread="thread",
            model="gpt-6-luna",
        ).to_payload()
        self.assertEqual(result["usage"]["inputTokens"], 50)
        self.assertEqual(result["usage"]["cachedInputTokens"], 20)
        self.assertEqual(result["usage"]["outputTokens"], 10)
        self.assertAlmostEqual(result["cost"]["amount"], 0.0000082)

    def test_unknown_cost_is_not_zero(self):
        self.assertIsNone(
            estimate(
                "unknown", {"inputTokens": 0, "cachedInputTokens": 0, "outputTokens": 0}
            )["amount"]
        )
        usage = {"inputTokens": 0, "cachedInputTokens": 0, "outputTokens": 0}
        self.assertEqual(estimate("gpt-6-luna", usage)["amount"], 0)
        self.assertIsNone(
            estimate("gpt-6-luna", {**usage, "cacheWriteInputTokens": 1})["amount"]
        )
        self.assertIsNone(
            estimate("gpt-6-luna", {**usage, "inputTokens": 300000})["amount"]
        )

    def test_conflicting_native_item_ids_are_visible(self):
        events = [
            {
                "raw": {
                    "method": "item/completed",
                    "params": {
                        "threadId": "t",
                        "turnId": "turn",
                        "item": {"id": "i", "text": text},
                    },
                },
                "received_at": "2026-10-15T00:00:00Z",
            }
            for text in ("first", "different")
        ]
        self.assertTrue(
            project(events).to_payload()["items"][0]["conflicting_receipts"]
        )

    def test_resume_initial_usage_does_not_invent_previous_turn(self):
        raw = {
            "method": "thread/tokenUsage/updated",
            "params": {
                "threadId": "thread",
                "turnId": "previous",
                "tokenUsage": {
                    "total": {
                        "inputTokens": 10,
                        "cachedInputTokens": 0,
                        "outputTokens": 0,
                    }
                },
            },
        }
        self.assertEqual(
            project([{"raw": raw, "received_at": "2026-10-15T00:00:00Z"}]).to_payload()[
                "turns"
            ],
            [],
        )

    def test_refused_attempt_cannot_adopt_another_resume(self):
        from laomedo.agents.activity.capture import ActivityCapture as RunnerCapture

        with tempfile.TemporaryDirectory() as directory:
            store = ActivityStore(Path(directory) / "activity.db")
            invocation = store.start(
                CaptureIdentity.from_values(
                    "alice", "flow", "refused", execution="graph"
                )
            )
            capture = RunnerCapture.__new__(RunnerCapture)
            capture.capture = ActivityInvocation(store=store, invocation_id=invocation)
            capture.timeout = 1
            capture.accepted = False
            capture.attempt_id = "22222222-2222-4222-8222-222222222222"
            capture.refused = threading.Event()
            capture.done = threading.Event()
            capture.done.set()
            capture.outcome = "failed"
            capture.feed = lambda *args: ActivityPage(
                run_id="runner",
                attempt_id=capture.attempt_id,
                available=False,
                records=[],
                next_after=0,
                has_more=False,
                closed=False,
                complete=None,
                reason="activity_attempt_not_available",
            )
            capture.observe("runner")
            page = store.read("alice", "flow", "refused", invocation)
            self.assertEqual(page["events"], [])
            self.assertEqual(page["run"]["status"], "failed")
            self.assertEqual(page["run"]["reason"], "dispatch_not_accepted")

    def test_accepted_attempt_baseline_and_boundary_are_authoritative(self):
        from laomedo.agents.activity.capture import ActivityCapture as RunnerCapture

        with tempfile.TemporaryDirectory() as directory:
            store = ActivityStore(Path(directory) / "activity.db")
            invocation = store.start(
                CaptureIdentity.from_values("alice", "flow", "agent", execution="graph")
            )
            capture = RunnerCapture.__new__(RunnerCapture)
            capture.capture = ActivityInvocation(store=store, invocation_id=invocation)
            capture.timeout = 1
            capture.accepted = False
            capture.attempt_id = "11111111-1111-4111-8111-111111111111"
            capture.refused = threading.Event()
            capture.done = threading.Event()
            capture.outcome = None
            projection = ActivityProjection(
                turns=[],
                items=[],
                threads=[],
                telemetry=[],
                telemetry_coverage="not observed",
                uncorrelated_thread_count=0,
                usage=None,
                usage_by_thread={},
                usage_points=[],
                clock="receipt time",
                cost={"amount": None},
                cost_reason="unobserved",
            )
            capture.feed = lambda *args: ActivityPage(
                run_id="runner",
                attempt_id=capture.attempt_id,
                available=True,
                records=[
                    ActivityRecord(
                        sequence=1,
                        occurred_at=None,
                        observed_at=datetime.now(timezone.utc),
                        event=MessageActivity(
                            message_id="message",
                            thread_id="thread",
                            role="assistant",
                            text="done",
                        ),
                    )
                ],
                next_after=1,
                has_more=False,
                closed=True,
                complete=True,
                reason=None,
                projection=projection,
                projection_revision=1,
                status="completed",
                thread_id="thread",
                model="gpt-6-luna",
                ended_at="2026-10-15T00:00:01Z",
            )
            capture.observe("runner")
            page = store.read("alice", "flow", "agent", invocation)
            self.assertEqual(page["run"]["status"], "completed")
            self.assertEqual(page["run"]["ended"], "2026-10-15T00:00:01Z")
            self.assertEqual(
                len(page["events"]), 2
            )  # shared projection plus common message record
            self.assertEqual(page["events"][0]["raw"]["method"], "activity/projection")
            self.assertEqual(
                page["events"][1]["raw"]["record"]["event"]["text"], "done"
            )
            other = store.start(
                CaptureIdentity.from_values(
                    "alice", "flow", "duplicate", execution="other"
                )
            )
            self.assertFalse(store.claim_attempt(other, "runner", capture.attempt_id))

    def test_capture_warning_is_partial_but_native_task_remains_completed(self):
        from laomedo.agents.activity.capture import ActivityCapture as RunnerCapture

        with tempfile.TemporaryDirectory() as directory:
            store = ActivityStore(Path(directory) / "activity.db")
            invocation = store.start(
                CaptureIdentity.from_values("alice", "flow", "agent", execution="graph")
            )
            capture = RunnerCapture.__new__(RunnerCapture)
            capture.capture = ActivityInvocation(store=store, invocation_id=invocation)
            capture.timeout = 1
            capture.accepted = False
            capture.attempt_id = "11111111-1111-4111-8111-111111111111"
            capture.refused = threading.Event()
            capture.done = threading.Event()
            capture.outcome = None
            capture.feed = lambda *args: ActivityPage(
                run_id="runner",
                attempt_id=capture.attempt_id,
                available=True,
                records=[],
                next_after=0,
                has_more=False,
                closed=True,
                complete=False,
                reason="claude_telemetry_capture_failed",
                status="completed",
                thread_id="thread",
                model="claude-sonnet-test",
                ended_at="2026-10-27T00:00:01Z",
            )
            capture.observe("runner")
            page = store.read("alice", "flow", "agent", invocation)
            self.assertEqual(page["run"]["status"], "completed")
            self.assertEqual(page["run"]["stream_state"], "partial")
            self.assertEqual(page["run"]["reason"], "claude_telemetry_capture_failed")

    def test_capture_uses_reported_completeness_without_provider_component_names(self):
        from laomedo.agents.activity.capture import ActivityCapture

        for complete, reason in (
            (True, None),
            (False, "native_message_snapshot_only"),
            (False, "opencode_native_snapshot_unavailable"),
        ):
            with (
                self.subTest(complete=complete, reason=reason),
                tempfile.TemporaryDirectory() as directory,
            ):
                store = ActivityStore(Path(directory) / "activity.db")
                invocation = store.start(
                    CaptureIdentity.from_values("alice", "flow", "agent")
                )
                capture = ActivityCapture.__new__(ActivityCapture)
                capture.capture = ActivityInvocation(
                    store=store, invocation_id=invocation
                )
                capture.timeout = 1
                capture.accepted = False
                capture.attempt_id = "11111111-1111-4111-8111-111111111111"
                capture.refused = threading.Event()
                capture.done = threading.Event()
                capture.outcome = None
                capture.feed = lambda *args: ActivityPage(
                    run_id="runner",
                    attempt_id=capture.attempt_id,
                    available=True,
                    records=[],
                    next_after=0,
                    has_more=False,
                    closed=True,
                    complete=complete,
                    reason=reason,
                    status="completed",
                    thread_id="native-session",
                )
                capture.observe("runner")
                page = store.read("alice", "flow", "agent", invocation)
                self.assertEqual(page["run"]["status"], "completed")
                self.assertEqual(
                    page["run"]["stream_state"], "complete" if complete else "partial"
                )
                self.assertEqual(page["run"]["reason"], reason)
