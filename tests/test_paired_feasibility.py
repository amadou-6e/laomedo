"""Zero-write feasibility development test, not acceptance evidence."""
import shutil
import unittest

from experiments.exp100.paired_feasibility import dry_run


@unittest.skipUnless(shutil.which('gh'), 'GitHub CLI unavailable')
class PairedFeasibilityTests(unittest.TestCase):
    def test_direct_cli_uses_one_synthetic_authenticated_loopback_read(self):
        result = dry_run()
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['exit_code'], 0)
        self.assertEqual(result['calls'], [{'method': 'GET',
                          'path': '/repos/example/disposable/issues'}])
        self.assertEqual(result['actual_writes'], 0)
        self.assertTrue(result['development_only'])
