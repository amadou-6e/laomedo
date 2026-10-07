"""No-network checks of the one-shot EXP-104 probe configuration."""

import unittest

from experiments.exp104 import live_probe


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


if __name__ == "__main__":
    unittest.main()
