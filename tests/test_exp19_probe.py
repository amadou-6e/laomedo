"""EXP-19's credential-free gate and result-binding observations."""

import tempfile
import unittest
from pathlib import Path

try:
    from experiments.exp19.probe import run_cases
except ModuleNotFoundError as error:
    if error.name != "experiments":
        raise
    run_cases = None


@unittest.skipUnless(run_cases is not None, "experiment source is not installed in the wheel")
class Exp19ProbeTests(unittest.TestCase):
    def test_ready_issue_retains_trace_and_local_candidate_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_cases(Path(directory))
        success = result["cases"]["ready_success"]
        self.assertEqual(success["outcome"], "completed")
        self.assertEqual(success["dispatch_attempts"], 1)
        self.assertEqual(success["receipt_count"], 2)
        self.assertEqual(success["projection_count"], 2)
        self.assertEqual(success["stream_state"], "complete")
        self.assertEqual(success["binding"]["run_id"], success["run_id"])
        self.assertEqual(success["binding"]["trace_id"], success["trace_id"])
        self.assertEqual(success["binding"]["graph_snapshot_id"],
                         success["graph_snapshot_id"])
        self.assertEqual(success["binding"]["input_digest"], success["input_digest"])
        self.assertEqual(success["binding"]["component_revision"],
                         success["component_revision"])
        self.assertIsNone(success["binding"]["target_pr"])
        self.assertEqual(success["pr_candidate"]["remote_count"], 0)
        self.assertIsNone(success["pr_candidate"]["target_pr"])
        self.assertEqual(len(success["pr_candidate"]["commit"]), 40)
        self.assertEqual(success["binding"]["candidate_commit"],
                         success["pr_candidate"]["commit"])
        self.assertEqual(success["binding"]["candidate_branch"],
                         success["pr_candidate"]["branch"])
        self.assertEqual(result["model_turns"], 0)
        self.assertEqual(result["github_writes"], 0)

    def test_stale_blocked_and_incomplete_sources_refuse_before_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            cases = run_cases(Path(directory))["cases"]
        for key, reason in (("stale_source", "source_snapshot_changed"),
                            ("opened_prerequisite", "source_not_ready"),
                            ("incomplete_blockers", "source_not_ready")):
            with self.subTest(key=key):
                case = cases[key]
                self.assertEqual(case["outcome"], "refused")
                self.assertEqual(case["reason"], reason)
                self.assertEqual(case["dispatch_attempts"], 0)
                self.assertIsNone(case["pr_candidate"])

    def test_failed_fake_agent_retains_partial_trace_without_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            failed = run_cases(Path(directory))["cases"]["fake_agent_failure"]
        self.assertEqual(failed["outcome"], "failed")
        self.assertEqual(failed["dispatch_attempts"], 1)
        self.assertEqual(failed["receipt_count"], 1)
        self.assertEqual(failed["projection_count"], 1)
        self.assertEqual(failed["stream_state"], "partial")
        self.assertIsNone(failed["pr_candidate"])
        self.assertIsNone(failed["binding"])


if __name__ == "__main__":
    unittest.main()
