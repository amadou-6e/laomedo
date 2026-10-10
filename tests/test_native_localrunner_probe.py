"""Credential-free prospective S13 controls; no model or live capture."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.exp104 import native_localrunner_worker as worker
from experiments.exp104 import native_localrunner_probe as probe
from experiments.exp104.native_localrunner_checks import IDENTITY, validate
from laomedo.local_runner import AppServer, RunnerError

ROOT = Path(__file__).resolve().parents[1]


class LocalRunnerProbeTests(unittest.TestCase):
    def test_review_rejects_other_identity_source_and_verdict(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "review.json"
            good = {"identity": IDENTITY, "source_sha": "a" * 40, "verdict": "approve"}
            path.write_text(json.dumps(good))
            self.assertEqual(probe.require_review(path, "a" * 40), sha256(path.read_bytes()).hexdigest())
            for key, value in (("identity", "old-consumed"), ("source_sha", "b" * 40), ("verdict", "disapprove")):
                bad = {**good, key: value}
                path.write_text(json.dumps(bad))
                with self.assertRaisesRegex(ValueError, "pre_run_review_required"):
                    probe.require_review(path, "a" * 40)

    def test_zero_turn_check_and_conflicting_records_are_falsifiable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            worker.zero_turns(root)
            (root / "turn-ledger.json").write_text('{"attempted_turns":1}')
            with self.assertRaisesRegex(ValueError, "unexpected_model_turn"):
                worker.zero_turns(root)
            self.assertNotIn("run_id", worker.identities("a", root))
            for number in (1, 2):
                directory = root / "runner/runs" / str(number)
                directory.mkdir(parents=True)
                (directory / "record.json").write_text(json.dumps({"run_id": str(number),
                    "github_scope": {"branch": IDENTITY + "-a"}}))
            with self.assertRaisesRegex(ValueError, "run_identity_conflict"):
                worker.identities("a", root)

    def test_worker_uses_real_transport_inheritance_zero_cap_and_refuses_turn(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "deadline").write_text("999999999")
            (root / "start-gate").touch()
            (root / "a-authorization.json").write_text('"trusted-reference"')
            (root / "skill-reference.json").write_text('{"skill_id":"fixture"}')

            class InspectRunner:
                def __init__(self, state, skill_store, source, **kwargs):
                    self.test = test
                    self.test.assertEqual(kwargs["max_model_turns"], 0)
                    self.test.assertTrue(kwargs["git_workspace"])
                    self.test.assertTrue(kwargs["supervise_containers"])
                    self.transport = kwargs["transport"]
                    self.test.assertTrue(issubclass(self.transport, AppServer))
                    self.state = state

                def _prepare(self, request):
                    self.test.assertEqual(request["github_authorization_ref"], "trusted-reference")
                    return {"run_id": "fixture-run"}

                def _execute(self, run_id, task, *, resume):
                    server = self.transport.__new__(self.transport)
                    for method in ("turn/start", "thread/start", "model/list"):
                        with self.test.assertRaisesRegex(RunnerError, "fixture_forbids_model_or_thread_request"):
                            server.request(method, {})
                    return {"run_id": run_id, "status": "failed", "error_category": "fixture_hold_finished_before_turn"}

            test = self
            with patch.object(worker, "LocalRunner", InspectRunner), patch.object(worker, "RunGrantAuthority"):
                worker.run(root, "a")
            self.assertTrue(json.loads((root / "a-initialized.json").read_bytes())["constructed"])
            self.assertEqual(json.loads((root / "a-finished.json").read_bytes())["model_turns"], 0)

    def test_control_mutations_reject_false_production_claims(self):
        # Synthetic positive fixture only, NOT new acceptance evidence.
        value = json.loads((ROOT / "experiments/exp104/native-managed-s12-b-observation.json").read_bytes())
        value["identity"] = IDENTITY
        value["shared_ledger_unchanged"] = True
        value["production"] = {}
        for index, side in ((0, "a"), (2, "b")):
            value["delivery"][side]["branch"] = IDENTITY + "-" + side
            value["delivery"][side]["marker"] = "laomedo:" + IDENTITY + ":pr:" + side
            value["provider_mutations"][index]["branch"] = IDENTITY + "-" + side
            value["production"][side] = {"production_launch": True, "native_initialize": True,
                "requests": ["initialize"], "model_turns": 0, "skill_exclusion_unchanged": True,
                "raw_events_sha256": "a" * 64, "record_sha256": "b" * 64,
                "grant_id": value["delivery"][side]["grant_id"]}
        self.assertTrue(validate(value))
        controls = (("native_initialize", False), ("production_launch", False),
            ("requests", ["initialize", "turn/start"]), ("model_turns", 1),
            ("skill_exclusion_unchanged", False), ("grant_id", "other"), ("raw_events_sha256", "bad"))
        for key, replacement in controls:
            with self.subTest(key=key):
                bad = deepcopy(value)
                bad["production"]["a"][key] = replacement
                with self.assertRaises(ValueError):
                    validate(bad)
        for section, key, replacement in (("loss", "revoked", value["loss"]["kill_completed"] + 61),
                ("loss", "attempts_after_denial", 99), ("loss", "b_grant_active", False),
                ("cleanup", "a", False)):
            bad = deepcopy(value)
            bad[section][key] = replacement
            with self.assertRaises(ValueError):
                validate(bad)
        value["shared_ledger_unchanged"] = False
        with self.assertRaisesRegex(ValueError, "model_budget_changed"):
            validate(value)
