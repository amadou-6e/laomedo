"""No-network checks of the one-shot EXP-104 probe configuration."""

import unittest
import importlib.util
from pathlib import Path
import tempfile


_PROBE = Path(__file__).resolve().parents[1] / "experiments" / "exp104" / "live_probe.py"
_SPEC = importlib.util.spec_from_file_location("exp104_live_probe_config", _PROBE)
live_probe = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(live_probe)


class LiveProbeConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.original_identity = live_probe.IDENTITY
        self.original_connection = live_probe.CONNECTION_ID
        self.addCleanup(live_probe.select_fresh_identity,
                        self.original_identity, self.original_connection)

    def test_fresh_identity_changes_every_effect_namespace(self):
        live_probe.select_fresh_identity("exp104-s3-20261007-01",
                                         "exp104-s3-selected-gh")
        self.assertEqual(live_probe.BRANCH_A, "exp104-s3-20261007-01-a")
        self.assertEqual(live_probe.RUN_B, "exp104-s3-20261007-01-run-b")
        self.assertEqual(live_probe.LEASE_C, "exp104-s3-20261007-01-lease-c")
        self.assertEqual(live_probe.CONTAINER_A,
                         "laomedo-exp104-s3-20261007-01-a")
        self.assertEqual(live_probe.CONNECTION_ID, "exp104-s3-selected-gh")

    def test_invalid_identity_is_rejected_before_run(self):
        with self.assertRaisesRegex(ValueError, "experiment_identity_invalid"):
            live_probe.select_fresh_identity("../old", "exp104-s3-selected-gh")
        self.assertEqual(live_probe.IDENTITY, self.original_identity)

    def test_scoped_candidate_refuses_without_selected_token_provenance(self):
        live_probe.select_fresh_identity("exp104-s3-20261007-01",
                                         "exp104-s3-selected-gh")
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "untouched-state"
            with self.assertRaisesRegex(RuntimeError,
                                        "scoped_identity_confirmation_required"):
                live_probe.run(state, Path(directory) / "missing-token", "0" * 40,
                               "GH", None)
            self.assertFalse(state.exists())

    def test_secret_canary_reports_only_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "safe.txt").write_text("safe", encoding="utf-8")
            (root / "bad.txt").write_text("hidden-test-secret", encoding="utf-8")
            self.assertEqual(live_probe._secret_canary(root, "hidden-test-secret"),
                             {"files_scanned": 2, "exact_token_hits": 1})


if __name__ == "__main__":
    unittest.main()
