"""Repeat the #108 controls without replacing the frozen observation."""

import unittest

from probe import run


class ConnectionExerciseTests(unittest.TestCase):
    def test_all_synthetic_controls(self):
        observation = run()
        self.assertEqual(observation["protocol"], "EXP-108-v1")
        self.assertEqual(observation["model_turns"], 0)
        self.assertEqual(observation["real_github_requests"], 0)
        self.assertGreaterEqual(len(observation["cases"]), 18)
        self.assertTrue(all(case["passed"] for case in observation["cases"]))


if __name__ == "__main__":
    unittest.main()
