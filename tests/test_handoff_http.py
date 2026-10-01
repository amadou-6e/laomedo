import io
import json
import threading
import time
import unittest
from unittest.mock import patch

from laomedo.handoff_http import RunnerAdapter
from laomedo.handoffs import HandoffError, envelope


class Response(io.BytesIO):
    def __enter__(self):
        return self
    def __exit__(self, *_):
        self.close()


class HttpTests(unittest.TestCase):
    def test_fresh_discards_foreign_native_ids_and_sensitive_runner_fields(self):
        item = envelope({"status": "completed", "provider": "opencode", "run_id": "source",
                         "thread_id": "foreign"}, {"provider": "codex", "model": "model", "effort": "low"},
                        "task", skills=[{"skill_id": "fixture", "revision_id": "sha256:" + "a" * 64}])
        def respond(req, timeout):
            payload = json.loads(req.data)
            self.assertNotIn("thread_id", payload)
            self.assertEqual(payload["skill_refs"][0]["tree_hash"], "sha256:" + "a" * 64)
            return Response(json.dumps({"run_id": "target", "status": "completed",
                                        "profile": "secret", "auth": "token"}).encode())
        adapter = RunnerAdapter({"codex": "http://localhost:8765"})
        with patch("laomedo.handoff_http.urlopen", side_effect=respond):
            output = adapter.dispatch(item, deadline=time.monotonic() + 10, cancelled=threading.Event())
        self.assertNotIn("secret", str(output))
        self.assertNotIn("token", str(output))
        self.assertEqual(output["provider"], "codex")

    def test_unsafe_url_and_unavailable_cancellation(self):
        with self.assertRaises(HandoffError):
            RunnerAdapter({"codex": "http://example.com"})
        self.assertFalse(RunnerAdapter({}).cancel("unknown")["cancel_acknowledged"])
