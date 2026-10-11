"""Local-only preflight for the frozen S7 Docker probe."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from laomedo.bundle_stage import (BundleStageError, PINNED_IMAGE_ID,
                                  _read_frozen, verify_frozen_bundle)

PROBE_PATH = (Path(__file__).resolve().parents[1] / "experiments" /
              "exp100" / "probe_stage_s7.py")
SPEC = importlib.util.spec_from_file_location("exp100_stage_s7", PROBE_PATH)
probe_stage_s7 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe_stage_s7)
fixture = probe_stage_s7.fixture


class ProbeS7Preflight(unittest.TestCase):
    def test_unknown_positive_preserves_case_without_key_error(self):
        observation = {"status": "unknown"}
        checkpoints = []

        def checkpoint():
            checkpoints.append(observation["cases"].copy())

        with patch.object(probe_stage_s7, "verify_frozen_bundle",
                          return_value={"status": "unknown"}), \
             patch.object(probe_stage_s7, "_run") as inspect:
            inspect.return_value.returncode = 1
            probe_stage_s7.run_once(observation, checkpoint)
        self.assertEqual(observation["status"], "failed")
        self.assertEqual(observation["cases"]["positive"]["result"],
                         {"status": "unknown"})
        self.assertGreaterEqual(len(checkpoints), 2)

    def test_two_synthetic_fixtures_and_wrong_commit_refusal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            positive = fixture(root, "positive")
            negative = fixture(root, "wrong-commit")
            self.assertNotEqual(positive["commit"], positive["baseline"])
            self.assertNotEqual(negative["commit"], negative["baseline"])
            self.assertNotEqual(positive["run_id"], negative["run_id"])
            attempt, frozen = _read_frozen(
                positive["runner"], positive["private"],
                positive["run_id"], positive["attempt_id"])
            self.assertTrue(attempt.is_dir())
            self.assertEqual(frozen["advertised_commit"], positive["commit"])
            calls = []

            def no_docker(*args, **kwargs):
                calls.append((args, kwargs))
                raise AssertionError("negative case reached Docker")

            with self.assertRaisesRegex(BundleStageError,
                                        "candidate_commit_mismatch"):
                verify_frozen_bundle(
                    negative["runner"], negative["private"],
                    run_id=negative["run_id"],
                    attempt_id=negative["attempt_id"],
                    baseline_bundle=negative["baseline_bundle"],
                    expected_baseline_sha256=negative["baseline_sha256"],
                    commit=negative["baseline"], image_id=PINNED_IMAGE_ID,
                    docker=no_docker)
            self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
