import hashlib
from pathlib import Path
import unittest
from uuid import uuid4

from laomedo.artifacts import ArtifactError, selections
from laomedo.local_runner import LocalRunner
import test_local_runner as fixtures


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.LocalRunnerTests("test_start_resume_and_fresh_workspace")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.runner = self.fixture.runner
        self.first = self.runner.start(self.fixture.request())
        self.ref = {"provider": "codex", "run_id": self.first["run_id"],
                    "snapshot_hash": self.first["post_run_hash"], "path": "agent.txt",
                    "content_hash": "sha256:" + hashlib.sha256(b"from-first-turn").hexdigest(),
                    "destination": "handoff/selected.txt"}

    def test_selected_bytes_independent_workspace_and_durable_provenance(self):
        selected = self.runner.select_artifacts(self.first["run_id"], ["agent.txt"])
        self.assertEqual(selected[0]["content_hash"], self.ref["content_hash"])
        self.assertEqual(selected[0]["destination"], "handoff/agent.txt")
        request = self.fixture.request()
        request["artifact_refs"] = [self.ref]
        request["handoff"] = {"execution_id": str(uuid4()), "step": 1,
            "source": {"provider": "codex", "run_id": self.first["run_id"]},
            "workspace_policy": "independent"}
        second = self.runner.start(request)
        snapshot = self.runner._run_dir(second["run_id"]) / "post-run"
        self.assertEqual((snapshot / "handoff/selected.txt").read_text(), "from-first-turn")
        self.assertFalse((self.runner._run_dir(self.first["run_id"]) / "post-run/handoff").exists())
        restarted = LocalRunner(self.runner.state, self.runner.store.root, self.fixture.source,
                                transport=fixtures.FakeServer, check_docker=False, max_model_turns=6)
        recovered = restarted.status(second["run_id"])
        self.assertEqual(recovered["handoff"], request["handoff"])
        self.assertEqual(recovered["imported_artifacts"], [self.ref])

    def test_wrong_hash_and_collisions_never_dispatch(self):
        before = len(fixtures.FakeServer.calls)
        for bad in [{**self.ref, "content_hash": "sha256:" + "b" * 64},
                    {**self.ref, "snapshot_hash": "sha256:" + "b" * 64},
                    {**self.ref, "destination": "task.txt"},
                    {**self.ref, "provider": "opencode"}]:
            with self.assertRaises(ArtifactError):
                self.runner.start({**self.fixture.request(), "artifact_refs": [bad]})
        self.assertEqual(len(fixtures.FakeServer.calls), before)

    def test_protected_paths_traversal_and_case_collisions_rejected(self):
        for path in ["../auth.json", ".codex/auth.json", "credentials.json", "x/id_rsa", "a\\b", "C:/secret"]:
            with self.assertRaises(ArtifactError):
                selections([{**self.ref, "path": path}])
        with self.assertRaisesRegex(ArtifactError, "conflict"):
            selections([self.ref, {**self.ref, "destination": "handoff/SELECTED.txt"}])

    def test_changed_source_snapshot_rejected(self):
        source = self.runner._run_dir(self.first["run_id"]) / "post-run/agent.txt"
        source.write_text("tampered")
        with self.assertRaisesRegex(ArtifactError, "snapshot"):
            self.runner.start({**self.fixture.request(), "artifact_refs": [self.ref]})

    def test_shared_workspace_and_hardlinks_are_not_imported(self):
        from laomedo.local_runner import RunnerError
        request = {**self.fixture.request(), "handoff": {"execution_id": str(uuid4()),
            "step": 1, "source": None, "workspace_policy": "shared"}}
        with self.assertRaisesRegex(RunnerError, "invalid_handoff"):
            self.runner.start(request)
        import os
        source = self.runner._run_dir(self.first["run_id"]) / "post-run/agent.txt"
        os.link(source, source.parent / "linked.txt")
        with self.assertRaisesRegex(RunnerError, "unsafe_workspace_entry"):
            self.runner.start({**self.fixture.request(), "artifact_refs": [self.ref]})
