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
