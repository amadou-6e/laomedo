import io
import json
import tempfile
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from laomedo.handoff_http import RunnerAdapter
from laomedo.handoffs import HandoffError, envelope


class Response(io.BytesIO):
    def __enter__(self):
        return self
    def __exit__(self, *_):
        self.close()


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.private = tempfile.TemporaryDirectory()
        self.addCleanup(self.private.cleanup)
        self.token_file = Path(self.private.name) / "token"
        self.token_file.write_text("a" * 64, encoding="utf-8")

    def adapter(self):
        return RunnerAdapter({"codex": "http://localhost:8765"},
                             {"codex": self.token_file})

    def test_fresh_discards_foreign_native_ids_and_sensitive_runner_fields(self):
        item = envelope({"status": "completed", "provider": "opencode", "run_id": "source",
                         "thread_id": "foreign"}, {"provider": "codex", "model": "model", "effort": "low"},
                        "task", skills=[{"skill_id": "fixture", "revision_id": "sha256:" + "a" * 64}])
        def respond(req, timeout):
            self.assertEqual(req.get_header("Authorization"), "Bearer " + "a" * 64)
            payload = json.loads(req.data)
            self.assertNotIn("thread_id", payload)
            self.assertEqual(payload["skill_refs"][0]["tree_hash"], "sha256:" + "a" * 64)
            return Response(json.dumps({"run_id": "target", "status": "completed",
                                        "profile": "secret", "auth": "token"}).encode())
        adapter = self.adapter()
        with patch("laomedo.handoff_http.urlopen", side_effect=respond):
            output = adapter.dispatch(item, deadline=time.monotonic() + 10, cancelled=threading.Event())
        self.assertNotIn("secret", str(output))
        self.assertNotIn("token", str(output))
        self.assertEqual(output["provider"], "codex")

    def test_unsafe_url_and_unavailable_cancellation(self):
        with self.assertRaises(HandoffError):
            RunnerAdapter({"codex": "http://example.com"})
        self.assertFalse(RunnerAdapter({}).cancel("unknown")["cancel_acknowledged"])

    def test_same_provider_resume_binds_thread_snapshot_model_and_skills(self):
        skill = {"skill_id": "fixture", "revision_id": "sha256:" + "a" * 64}
        origin = {"provider": "codex", "status": "completed", "run_id": "source",
                  "thread_id": "thread", "post_run_hash": "sha256:" + "b" * 64,
                  "model": "model", "effort": "low", "skills": [skill]}
        target = {"provider": "codex", "model": "model", "effort": "low"}
        item = envelope(origin, target, "continue", skills=[skill], operation="resume")
        def respond(req, timeout):
            self.assertTrue(req.full_url.endswith("/source/resume"))
            payload = json.loads(req.data)
            self.assertEqual(payload["expected_thread_id"], "thread")
            self.assertEqual(payload["expected_post_run_hash"], origin["post_run_hash"])
            self.assertNotIn("skill_refs", payload)
            return Response(json.dumps({"run_id": "source", "status": "completed"}).encode())
        adapter = self.adapter()
        with patch("laomedo.handoff_http.urlopen", side_effect=respond):
            adapter.dispatch(item, deadline=time.monotonic() + 10, cancelled=threading.Event())
        with self.assertRaisesRegex(HandoffError, "skill_binding"):
            envelope(origin, target, "continue", skills=[{**skill, "skill_id": "different"}], operation="resume")
        with self.assertRaisesRegex(HandoffError, "model_effort"):
            adapter.dispatch({**item, "target": {**target, "model": "different"}},
                             deadline=time.monotonic() + 10, cancelled=threading.Event())

    def test_definite_http_rejection_does_not_claim_runner_id(self):
        item = envelope(None, {"provider": "codex", "model": "model", "effort": "low"},
                        "task", skills=[{"skill_id": "fixture", "revision_id": "sha256:" + "a" * 64}])
        error = HTTPError("http://localhost:8765/v1/runs", 400, "Bad Request", {},
                          io.BytesIO(b'{"error_category":"invalid_skill"}'))
        with patch("laomedo.handoff_http.urlopen", side_effect=error):
            result = self.adapter().dispatch(item, deadline=time.monotonic() + 10,
                                             cancelled=threading.Event())
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["error_category"], "invalid_skill")
        self.assertNotIn("run_id", result)

        uncertain = HTTPError("http://localhost:8765/v1/runs", 502, "Gateway Error", {},
                              io.BytesIO(b'{"error_category":"transport_closed"}'))
        with patch("laomedo.handoff_http.urlopen", side_effect=uncertain):
            with self.assertRaisesRegex(HandoffError, "invalid_runner_response"):
                self.adapter().dispatch(item, deadline=time.monotonic() + 10,
                                        cancelled=threading.Event())
