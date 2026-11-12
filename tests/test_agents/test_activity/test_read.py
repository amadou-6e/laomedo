"""Exercise real provider reads against retained evidence, without native execution."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import json
import unittest

from laomedo.agents.agents.codex.agent import CodexAgent
from laomedo.agents.agents.base.utils import _json
from laomedo.agents.errors import RunnerError
from laomedo.agents.agents.opencode.agent import OpenCodeAgent
from laomedo.agents.activity.store import ActivityStore
from laomedo.agents.activity.models import CaptureIdentity
from laomedo.agents.activity.models import ActivityInvocation
from laomedo.agents.activity.capture import ActivityCapture
from laomedo.agents.activity.projection import project
from laomedo.host.runner.http.server import RunnerServer
from unittest.mock import patch
from urllib.request import build_opener, ProxyHandler
import threading


class ActivityReadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.agent = object.__new__(CodexAgent)
        self.agent.state = Path(self.temporary.name)
        self.run = str(uuid4())
        self.attempt = str(uuid4())
        self.root = self.agent.state / "runs" / self.run
        (self.root / "activity-attempts").mkdir(parents=True)
        _json(
            self.root / "record.json",
            {
                "run_id": self.run,
                "status": "running",
                "thread_id": "thread",
                "effective_model": "test",
            },
        )
        self.boundary = {
            "id": self.attempt,
            "native_start": 0,
            "otel_start": 0,
            "native_end": None,
            "otel_end": None,
            "fresh_thread": True,
            "usage_baseline": {},
            "status": "running",
            "ended_at": None,
        }
        self.save_boundary()

    def save_boundary(self):
        _json(self.root / "activity-attempts" / (self.attempt + ".json"), self.boundary)

    def append(self, method, params):
        with (self.root / "activity-events.jsonl").open(
            "a", encoding="utf-8"
        ) as stream:
            stream.write(
                json.dumps(
                    {
                        "received_at": "2026-11-11T08:00:00+00:00",
                        "event": {"method": method, "params": params},
                    }
                )
                + "\n"
            )

    def message(self, text):
        self.append(
            "item/started",
            {
                "threadId": "thread",
                "turnId": "turn",
                "item": {"id": "message", "type": "agentMessage", "text": text},
            },
        )

    def read(self, **kwargs):
        return self.agent.read_activity(self.run, self.attempt, **kwargs)

    def test_streaming_replacements_retry_and_restart_keep_sequences(self):
        self.message("a")
        first = self.read()
        self.assertEqual(first.records[0].event.text, "a")
        self.append(
            "item/agentMessage/delta",
            {"threadId": "thread", "itemId": "message", "delta": "b"},
        )
        second = self.read(after=first.next_after)
        self.assertEqual(second.records[0].event.text, "ab")
        self.assertGreater(second.records[0].sequence, first.next_after)
        replay = self.read()
        self.assertEqual([row.event.text for row in replay.records], ["a", "ab"])
        self.assertEqual(self.read().records, replay.records)
        restarted = object.__new__(CodexAgent)
        restarted.state = self.agent.state
        self.assertEqual(
            restarted.read_activity(self.run, self.attempt).records, replay.records
        )
        self.assertFalse(second.closed)
        self.assertIsNone(second.complete)

    def test_concurrent_readers_do_not_allocate_duplicate_versions(self):
        self.message("hello")
        with ThreadPoolExecutor(max_workers=4) as pool:
            pages = list(pool.map(lambda _: self.read(), range(8)))
        self.assertTrue(all(len(page.records) == 1 for page in pages))
        self.assertTrue(all(page.records == pages[0].records for page in pages))

    def test_closed_attempt_excludes_following_resume_and_drains_pages(self):
        self.message("first")
        self.append(
            "turn/completed",
            {"threadId": "thread", "turn": {"id": "turn", "status": "completed"}},
        )
        self.boundary.update(native_end=2, otel_end=0, status="completed")
        self.save_boundary()
        self.message("next attempt must not leak")
        page = self.read(limit=1)
        self.assertTrue(page.closed)
        self.assertTrue(page.complete)
        self.assertEqual(page.records[0].event.text, "first")
        self.assertNotIn("next attempt", json.dumps(page.projection.to_payload()))

    def test_missing_attempt_and_invalid_cursor_are_explicit(self):
        page = self.agent.read_activity(self.run, str(uuid4()))
        self.assertFalse(page.available)
        self.assertIsNone(page.complete)
        for arguments in (
            {"after": -1},
            {"after": True},
            {"limit": 0},
            {"limit": 201},
            {"after": 10},
        ):
            with (
                self.subTest(arguments=arguments),
                self.assertRaisesRegex(RunnerError, "invalid_activity_cursor"),
            ):
                self.read(**arguments)

    def test_half_closed_metadata_is_not_capture_completion(self):
        self.boundary.update(native_end=0)
        self.save_boundary()
        with self.assertRaisesRegex(RunnerError, "activity_attempt_identity_mismatch"):
            self.read()

    def test_partial_trailing_line_is_not_consumed(self):
        self.message("first")
        with (self.root / "activity-events.jsonl").open("a") as stream:
            stream.write('{"received_at":')
        page = self.read()
        self.assertEqual([row.event.text for row in page.records], ["first"])
        self.assertFalse(page.closed)

    def test_partial_tool_output_and_usage_revisions_are_replacements(self):
        self.append(
            "item/started",
            {
                "threadId": "thread",
                "turnId": "turn",
                "item": {
                    "id": "tool",
                    "type": "commandExecution",
                    "command": "pytest",
                    "aggregatedOutput": "a",
                },
            },
        )
        first = self.read()
        self.append(
            "item/commandExecution/outputDelta",
            {"threadId": "thread", "itemId": "tool", "delta": "b"},
        )
        second = self.read(after=first.next_after)
        result = next(
            row.event for row in second.records if row.event.kind == "tool_result"
        )
        self.assertEqual((result.output, result.status), ("ab", "running"))
        for amount in (3, 5):
            self.append(
                "thread/tokenUsage/updated",
                {
                    "threadId": "thread",
                    "tokenUsage": {
                        "total": {
                            "inputTokens": amount,
                            "outputTokens": 0,
                            "cachedInputTokens": 0,
                            "cacheWriteInputTokens": 0,
                            "reasoningOutputTokens": 0,
                            "totalTokens": amount,
                        }
                    },
                },
            )
            page = self.read(after=second.next_after)
            usage = next(row.event for row in page.records if row.event.kind == "usage")
            self.assertEqual(usage.input_tokens, amount)
            second = page

    def test_sealed_missing_evidence_is_partial_and_boundary_cannot_be_rewritten(self):
        self.message("first")
        self.append(
            "turn/completed",
            {"threadId": "thread", "turn": {"id": "turn", "status": "completed"}},
        )
        self.boundary.update(native_end=3, otel_end=0, status="completed")
        self.save_boundary()
        page = self.read()
        self.assertTrue(page.closed)
        self.assertFalse(page.complete)
        self.assertEqual(page.reason, "activity_capture_incomplete")
        self.boundary["native_start"] = 1
        self.save_boundary()
        with self.assertRaisesRegex(RunnerError, "activity_attempt_identity_mismatch"):
            self.read()

    def test_opencode_completeness_is_decided_by_its_provider_read(self):
        agent = object.__new__(OpenCodeAgent)
        agent.state = self.agent.state
        self.boundary.update(native_end=0, otel_end=0, status="completed")
        for fields, complete, reason in (
            ({"capture_complete": True}, True, None),
            ({"capture_complete": False}, False, "native_message_snapshot_only"),
            (
                {
                    "capture_complete": True,
                    "capture_error": "opencode_native_snapshot_unavailable",
                },
                False,
                "opencode_native_snapshot_unavailable",
            ),
        ):
            with self.subTest(fields=fields):
                self.boundary.pop("capture_error", None)
                self.boundary.update(fields)
                self.save_boundary()
                page = agent.read_activity(self.run, self.attempt)
                self.assertEqual((page.complete, page.reason), (complete, reason))

    def test_actual_http_capture_store_and_display_need_no_application_parser(self):
        self.message("saved common message")
        self.append(
            "turn/completed",
            {"threadId": "thread", "turn": {"id": "turn", "status": "completed"}},
        )
        self.boundary.update(native_end=2, otel_end=0, status="completed")
        self.save_boundary()
        self.agent.api_token = "a" * 64
        server = RunnerServer(self.agent, port=0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            store = ActivityStore(self.agent.state / "application.db")
            invocation = store.start(
                CaptureIdentity.from_values(
                    "alice", "flow", "node", provider="codex-cli"
                )
            )
            capture = ActivityCapture.__new__(ActivityCapture)
            capture.capture = ActivityInvocation(store=store, invocation_id=invocation)
            capture.timeout = 3
            capture.attempt_id = self.attempt
            capture.accepted = False
            capture.refused = threading.Event()
            capture.done = threading.Event()
            capture.outcome = None
            capture.base = "http://127.0.0.1:" + str(server.server_port)
            capture.token = self.agent.api_token
            capture.opener = build_opener(ProxyHandler({}))
            capture.observe(self.run)
            saved = store.read("alice", "flow", "node", invocation)
            self.assertEqual(saved["run"]["stream_state"], "complete")
            with patch(
                "laomedo.agents.activity.legacy.project_retained",
                side_effect=AssertionError(
                    "application must not parse native evidence"
                ),
            ):
                payload = project(
                    saved["events"], provider="not-needed-for-normalized-history"
                )
            self.assertEqual(
                payload["items"][0]["item"]["text"], "saved common message"
            )
            with self.assertRaises(LookupError):
                store.read("bob", "flow", "node", invocation)
        finally:
            server.shutdown()
            worker.join(timeout=5)
            server.server_close()

    def test_retraction_and_metadata_only_revision_preserve_old_records(self):
        from laomedo.agents.activity.normalizer import ActivityNormalizer
        from laomedo.agents.activity.models import ActivityProjection
        import sqlite3

        normalizer = ActivityNormalizer(self.agent, None)
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE TABLE records(attempt,sequence,body)")
            db.execute(
                "CREATE TABLE snapshots(attempt PRIMARY KEY,state,projection,revision)"
            )
            empty = self.agent.read_activity(self.run, self.attempt).projection
            initial = empty.model_copy(
                update={
                    "items": [
                        {
                            "id": "message",
                            "thread": "thread",
                            "item": {"type": "agentMessage", "text": "first"},
                        }
                    ]
                }
            )
            self.assertEqual(normalizer._publish(db, self.attempt, initial), (1, 1))
            self.assertEqual(normalizer._publish(db, self.attempt, empty), (2, 2))
            records = [
                json.loads(row[0])
                for row in db.execute("SELECT body FROM records ORDER BY sequence")
            ]
            self.assertFalse(records[0]["event"]["removed"])
            self.assertTrue(records[1]["event"]["removed"])
            changed = empty.model_copy(update={"diagnostics": {"capture": "late"}})
            self.assertEqual(normalizer._publish(db, self.attempt, changed), (2, 3))

    def test_malformed_source_and_corrupt_journal_are_explicit_failures(self):
        source = self.root / "activity-events.jsonl"
        source.write_text("not json\n", encoding="utf-8")
        with self.assertRaises(RunnerError) as caught:
            self.agent.read_activity(self.run, self.attempt)
        self.assertEqual(caught.exception.code, "activity_normalization_failed")
        source.write_text("", encoding="utf-8")
        (self.root / "activity-normalized.db").write_bytes(b"not a database")
        with self.assertRaises(RunnerError) as caught:
            self.agent.read_activity(self.run, self.attempt)
        self.assertEqual(caught.exception.code, "activity_journal_unavailable")

    def test_projection_budget_keeps_a_partial_readable_page(self):
        with patch(
            "laomedo.agents.activity.normalizer.ActivityNormalizer.MAX_BYTES", 1
        ):
            page = self.read()
        self.assertFalse(page.closed)
        self.assertIsNone(page.complete)
        self.assertEqual(page.reason, "activity_projection_limit")

    def test_long_source_preserves_prefix_and_sealed_incompleteness(self):
        self.message("a")
        event = {
            "received_at": "2026-11-11T08:00:00+00:00",
            "event": {
                "method": "item/agentMessage/delta",
                "params": {"threadId": "thread", "itemId": "message", "delta": "b"},
            },
        }
        with (self.root / "activity-events.jsonl").open(
            "a", encoding="utf-8"
        ) as stream:
            stream.write((json.dumps(event) + "\n") * 20001)
        self.boundary.update(native_end=20002, otel_end=0, status="completed")
        self.save_boundary()
        page = self.read()
        self.assertTrue(page.closed)
        self.assertFalse(page.complete)
        self.assertEqual(page.reason, "activity_projection_limit")
        self.assertEqual(len(page.records[0].event.text), 20000)
        self.assertEqual(page.records, self.read().records)

    def test_journal_budget_keeps_replay_and_does_not_block_resume(self):
        from laomedo.agents.activity.normalizer import ActivityNormalizer

        self.message("a")
        initial = self.read()
        self.append(
            "item/agentMessage/delta",
            {
                "threadId": "thread",
                "itemId": "message",
                "delta": "much longer replacement",
            },
        )
        with patch.object(ActivityNormalizer, "MAX_JOURNAL_BYTES", 1):
            partial = self.read()
        self.assertEqual(partial.records, initial.records)
        self.assertEqual(partial.reason, "activity_projection_limit")
        self.attempt = str(uuid4())
        self.boundary.update(id=self.attempt, native_start=2)
        self.save_boundary()
        self.message("new resumed attempt")
        resumed = self.read()
        self.assertEqual(resumed.records[0].sequence, 1)
        self.assertEqual(resumed.records[0].event.text, "new resumed attempt")
        self.assertIsNone(resumed.reason)

    def test_wire_diagnostics_omission_and_reasoning_not_an_answer(self):
        self.append(
            "item/started",
            {
                "threadId": "thread",
                "turnId": "turn",
                "item": {
                    "id": "reason",
                    "type": "reasoning",
                    "text": "private reasoning",
                },
            },
        )
        self.message("actual answer")
        page = self.read()
        self.assertEqual([row.event.text for row in page.records], ["actual answer"])
        from laomedo.agents.activity.models import ActivityPage

        wire = page.to_payload()
        self.assertEqual(
            "diagnostics" in wire["projection"],
            "diagnostics" in page.projection.to_payload(),
        )
        self.assertEqual(
            ActivityPage.model_validate_json(json.dumps(wire)).projection.to_payload(),
            page.projection.to_payload(),
        )

    def test_resumed_usage_record_subtracts_cumulative_baseline(self):
        self.boundary.update(
            fresh_thread=False,
            usage_baseline={
                "thread": {"total": {"inputTokens": 100, "outputTokens": 20}}
            },
        )
        self.save_boundary()
        self.append(
            "thread/tokenUsage/updated",
            {
                "threadId": "thread",
                "tokenUsage": {"total": {"inputTokens": 130, "outputTokens": 25}},
            },
        )
        usage = [row.event for row in self.read().records if row.event.kind == "usage"][
            0
        ]
        self.assertEqual((usage.input_tokens, usage.output_tokens), (30, 5))

    def test_http_page_projection_preserves_omitted_and_explicit_diagnostics(self):
        from laomedo.agents.activity.models import ActivityProjection
        from laomedo.agents.activity.models import ActivityPage

        page = self.read()
        payload = page.projection.to_payload()
        payload.pop("diagnostics", None)
        omitted = page.model_copy(
            update={"projection": ActivityProjection.model_validate(payload)}
        )
        wire = omitted.to_payload()
        self.assertNotIn("diagnostics", wire["projection"])
        self.assertNotIn(
            "diagnostics",
            ActivityPage.model_validate_json(json.dumps(wire)).projection.to_payload(),
        )
        explicit = page.model_copy(
            update={
                "projection": ActivityProjection.model_validate(
                    {**payload, "diagnostics": None}
                )
            }
        )
        self.assertIn(
            "diagnostics",
            ActivityPage.model_validate_json(
                json.dumps(explicit.to_payload())
            ).projection.to_payload(),
        )
