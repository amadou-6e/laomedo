"""Initial native status never becomes a model prompt; fixtures, not live acceptance."""

import unittest
from laomedo.agents.agents.base.agent import BaseAgent
from laomedo.agents.errors import RunnerError
from test_agents.test_runtime.utils import prepare_runner
from test_agents.test_runtime.commands import InitialStatusTransport
from test_agents.test_runtime.transport import FakeServer


class InitialStatusTests(unittest.TestCase):
    def setUp(self):
        prepare_runner(self)
        FakeServer.turn_inputs.clear()

    def request(self):
        return {
            "task": "/status",
            "model": "test-model",
            "effort": "low",
            "initial_native_command": "status",
        }

    def test_control_only_start_retains_resumable_thread_without_a_model_turn(self):
        self.runner.transport = InitialStatusTransport
        result = self.runner.start(self.request())
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["turns"], [])
        self.assertEqual(FakeServer.turn_inputs, [])
        self.assertEqual(result["thread_id"], "native-thread")
        self.assertTrue(result["post_run_hash"])
        self.assertEqual(len(result["native_command_receipts"]), 1)
        following = self.runner.resume(
            result["run_id"],
            "Hello",
            expected_thread_id=result["thread_id"],
            expected_post_run_hash=result["post_run_hash"],
            model="test-model",
            effort="low",
        )
        self.assertEqual(following["status"], "completed")
        self.assertEqual(following["thread_id"], result["thread_id"])
        self.assertEqual(FakeServer.turn_inputs, ["Hello"])

    def test_missing_native_command_capability_refuses_before_model_prompt(self):
        result = self.runner.start(self.request())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_category"], "native_command_not_supported")
        self.assertEqual(FakeServer.turn_inputs, [])

    def test_other_providers_default_refusal_and_codex_exact_initial_mode(self):
        with self.assertRaisesRegex(RunnerError, "native_command_not_supported"):
            BaseAgent.prepare_initial_command(self.runner, self.request())
        for change in (
            {"initial_native_command": "review"},
            {"task": "Please run /status"},
            {"github_authorization_ref": "scope"},
            {"output_requirements": {}},
        ):
            with self.subTest(change=change), self.assertRaises(RunnerError):
                self.runner.start({**self.request(), **change})
        self.assertEqual(FakeServer.turn_inputs, [])
