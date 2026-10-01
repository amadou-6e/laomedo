"""No credentials or model requests: verify OpenCode protocol and persistence."""

import unittest

import test_local_runner as fixtures
from laomedo.opencode_runner import OpenCodeRunner, RunnerError, normalize_message


class Backend:
    sessions = 0

    def __init__(self, workspace, evidence):
        self.workspace = workspace
        self.log = (evidence / "raw-events.jsonl").open("a")

    def call(self, method, path, payload=None):
        self.log.write(path + "\n")
        self.log.flush()
        if path == "/global/health":
            return {"healthy": True, "version": "1.18.33"}
        if path == "/provider":
            return {"connected": ["test"], "all": [{"id": "test", "models": {"model": {}}}]}
        if path == "/session":
            type(self).sessions += 1
            return {"id": "ses_test" + str(self.sessions)}
        if path.endswith("/message"):
            (self.workspace / "output.txt").write_text("observed fixture")
            return {"info": {"id": "msg_fixture", "role": "assistant", "time": {"completed": 1},
                             "sessionID": path.split("/")[2], "providerID": "test", "modelID": "model"},
                    "parts": [{"type": "text", "text": "fixture answer"},
                              {"type": "tool", "tool": "skill", "callID": "tool1",
                               "state": {"status": "completed", "input": {"name": "sample"},
                                         "output": "skill body"}}]}
        raise AssertionError(path)

    def close(self):
        self.log.close()


class OpenCodeTests(unittest.TestCase):
    def setUp(self):
        # Reuse only the fixture setup, not the Codex provider test cases.
        fixtures.LocalRunnerTests.setUp(self)
        self.runner = OpenCodeRunner(self.root.parent / (self.root.name + "-runner"),
            self.root.parent / (self.root.name + "-skill-store"), self.source,
            max_model_turns=3, transport_factory=Backend)
        self.addCleanup(lambda: __import__("shutil").rmtree(self.runner.state, ignore_errors=True))
        self.payload = {"task": "Read skill", "model": "test/model", "effort": "default",
                        "skill_ref": {"skill_id": "sample", "revision_id": self.revision["revision_id"],
                                      "tree_hash": self.revision["tree_hash"]}}

    def test_fresh_restart_resume_and_evidence(self):
        run = self.runner.start(self.payload)
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["skills"][0]["use_evidence"], "native_skill_tool_completed")
        self.assertIsNone(run["usage"])
        restarted = OpenCodeRunner(self.runner.state, self.runner.store.root, self.source,
            max_model_turns=3, transport_factory=Backend)
        resumed = restarted.resume(run["run_id"], "Continue", expected_post_run_hash=run["post_run_hash"],
            expected_thread_id=run["thread_id"], model="test/model", effort="default")
        self.assertEqual(resumed["thread_id"], run["thread_id"])
        self.assertEqual(len(resumed["turns"]), 2)
        fresh = restarted.start(self.payload)
        self.assertNotEqual(fresh["run_id"], run["run_id"])
        self.assertNotEqual(fresh["thread_id"], run["thread_id"])

    def test_unsupported_effort_before_dispatch(self):
        with self.assertRaisesRegex(RunnerError, "unsupported_opencode_effort"):
            self.runner.start({**self.payload, "effort": "high"})

    def test_production_transport_is_not_silently_enabled(self):
        self.runner.transport_factory = None
        with self.assertRaisesRegex(RunnerError, "opencode_isolated_transport_required"):
            self.runner.start(self.payload)
        self.assertEqual(self.runner.preflight()["status"], "blocked")

    def test_running_tool_is_not_completed(self):
        with self.assertRaisesRegex(RunnerError, "opencode_outstanding_tool"):
            normalize_message({"info": {"role": "assistant", "time": {"completed": 1}},
                "parts": [{"type": "tool", "state": {"status": "running"}}]}, [])

    def test_multiple_skills_remain_pinned(self):
        second = self.runner.store.import_skill("second", self.skill_source)
        refs = [self.payload["skill_ref"], {"skill_id": "second", "revision_id": second["revision_id"],
                                         "tree_hash": second["tree_hash"]}]
        payload = {key: value for key, value in self.payload.items() if key != "skill_ref"}
        run = self.runner.start({**payload, "skill_refs": refs})
        self.assertEqual(run["status"], "completed")
        self.assertEqual([item["skill_id"] for item in run["skills"]], ["sample", "second"])
        self.assertEqual(run["skills"][1]["use_evidence"], "offered")

    def test_resume_rejects_workspace_mutation(self):
        run = self.runner.start(self.payload)
        args = {"expected_post_run_hash": run["post_run_hash"], "expected_thread_id": run["thread_id"],
                "model": "test/model", "effort": "default"}
        (self.runner._run_dir(run["run_id"]) / "workspace/output.txt").write_text("changed")
        with self.assertRaisesRegex(RunnerError, "workspace_changed_since_snapshot"):
            self.runner.resume(run["run_id"], "Continue", **args)


if __name__ == "__main__":
    unittest.main()
