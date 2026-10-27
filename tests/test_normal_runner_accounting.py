"""Internal accounting regressions, with no Docker or model requests."""
import unittest
import shutil
from laomedo.agents.local_runner import LocalRunner, _json
from laomedo.agents.providers.opencode_runner import OpenCodeRunner
import test_local_runner as fixtures

class NormalRunnerAccountingTests(unittest.TestCase):
    def setUp(self):
        fixtures.LocalRunnerTests.setUp(self)

    def test_normal_codex_and_opencode_ignore_historical_experiment_allowances(self):
        for runner_type in (LocalRunner,OpenCodeRunner):
            with self.subTest(provider=runner_type.__name__):
                runner=runner_type(self.root.parent/(self.root.name+"-runner"),self.runner.store.root,self.source,
                    **({"check_docker":False} if runner_type is LocalRunner else {}))
                self.addCleanup(shutil.rmtree,runner.state,ignore_errors=True)
                historical=runner.state/"turn-ledger.json"
                for old in ({"attempted_turns":100,"max_authorized_turns":0},{"attempted_turns":"invalid historic evidence"}):
                    _json(historical,old);before=historical.read_bytes()
                    runner._turn_available()
                    previous=runner._reserve_turn()
                    self.assertGreater(runner._reserve_turn(),previous)
                    self.assertEqual(historical.read_bytes(),before)
                self.assertFalse(hasattr(runner,"max_model_turns"))
                self.assertTrue((runner.state/"attempt-count.json").exists())
