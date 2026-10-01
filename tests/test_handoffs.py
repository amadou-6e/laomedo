import unittest
from laomedo.handoffs import BoundedController, HandoffError, envelope


TARGET = {"provider": "codex", "agent": "writer"}
SKILLS = [{"skill_id": "fixture", "revision_id": "sha256:" + "a" * 64}]


class Adapter:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.calls = []
        self.cancellations = []

    def dispatch(self, item, **kwargs):
        self.calls.append(item)
        answer = next(self.answers)
        if isinstance(answer, Exception):
            raise answer
        return {"provider": "codex", "run_id": str(len(self.calls)),
                "status": "failed" if answer is None else "completed", "answer": answer}

    def cancel(self, execution_id):
        self.cancellations.append(execution_id)


class HandoffTests(unittest.TestCase):
    def controller(self, answers, **kwargs):
        adapter = Adapter(answers)
        return BoundedController(adapter, max_iterations=kwargs.pop("max_iterations", 5),
                                 turn_budget=kwargs.pop("turn_budget", 5),
                                 timeout_seconds=10, **kwargs)

    def run_chain(self, controller, **kwargs):
        return controller.run([TARGET, TARGET], "start", SKILLS,
                              success=lambda r: r["answer"] == "done", **kwargs)

    def test_chain_receives_answer_once_with_no_thread_or_credentials(self):
        c = self.controller(["selected", "end"])
        result = self.run_chain(c)
        self.assertEqual(result["stop_reason"], "chain_completed")
        self.assertEqual(len(c.adapter.calls), 2)
        self.assertEqual(c.adapter.calls[1]["task"], "selected")
        self.assertIsNone(c.adapter.calls[1]["prior"])
        self.assertEqual(c.adapter.calls[1]["workspace_policy"], "independent")
        with self.assertRaisesRegex(HandoffError, "already_started"):
            self.run_chain(c)

    def test_failure_stops_before_second(self):
        c = self.controller([None])
        self.assertEqual(self.run_chain(c)["stop_reason"], "agent_failed")
        self.assertEqual(len(c.adapter.calls), 1)

    def test_success(self):
        self.assertEqual(self.run_chain(self.controller(["done"]), loop=True)["stop_reason"], "success")

    def test_iteration_and_turn_caps_independently(self):
        for field, reason in [("max_iterations", "iteration_limit"), ("turn_budget", "turn_budget")]:
            c = self.controller(["one", "two"], **{field: 1})
            self.assertEqual(self.run_chain(c, loop=True)["stop_reason"], reason)
            self.assertEqual(c.submitted, 1)

    def test_deadline_without_send(self):
        now = [0]
        c = self.controller([], clock=lambda: now[0])
        now[0] = 11
        self.assertEqual(self.run_chain(c)["stop_reason"], "deadline")
        self.assertEqual(c.submitted, 0)

    def test_cancel(self):
        c = self.controller([])
        c.cancel()
        self.assertEqual(self.run_chain(c)["stop_reason"], "cancelled")
        self.assertEqual(c.adapter.cancellations, [c.execution_id])

    def test_no_progress(self):
        c = self.controller(["repeat", "repeat"])
        self.assertEqual(self.run_chain(c, loop=True)["stop_reason"], "no_progress")

    def test_uncertain_submission_not_retried(self):
        c = self.controller([TimeoutError("private detail")])
        result = self.run_chain(c)
        self.assertEqual(result["stop_reason"], "dispatch_uncertain")
        self.assertEqual(result["submitted_turns"], 1)
        self.assertNotIn("private detail", str(result))

    def test_foreign_resume_and_artifacts_fail_closed(self):
        origin = {"provider": "codex", "run_id": "a", "status": "completed", "auth": "secret"}
        with self.assertRaisesRegex(HandoffError, "foreign"):
            envelope(origin, {"provider": "opencode"}, "task", skills=SKILLS, operation="resume")
        with self.assertRaisesRegex(HandoffError, "artifact_transfer"):
            envelope(origin, TARGET, "task", skills=SKILLS, artifacts=["auth.json"])
        result = envelope(origin, TARGET, "task", skills=SKILLS)
        self.assertNotIn("secret", str(result))


if __name__ == "__main__":
    unittest.main()
