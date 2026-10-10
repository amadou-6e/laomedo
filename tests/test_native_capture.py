"""Mutation controls of capture assessment, not campaign execution/evidence."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("native_capture", ROOT / "experiments/exp100/probe_native_capture.py")
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


class NativeCaptureChecks(unittest.TestCase):
    def test_committed_observations_are_pinned_and_never_reexecuted(self):
        cases = [("A", "a37d176dc91b216e904d597ead1434002468cb5cc19b52a824a3b2698b90af99"),
                 ("B", "99122e350db228ef1e40c0efd42582a73753e809946db2dcacc74e651eddec34")]
        for case, digest in cases:
            data = (ROOT / f"experiments/exp100/S10-{case}-OBSERVATION.json").read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest)
            observation = json.loads(data)
            self.assertEqual(observation["model_turns"], 0)
            self.assertEqual(observation["real_provider_calls"], 0)
            self.assertTrue(observation["cleanup_verified"])
            if case == "B":
                capture.validate_observation(observation)
                self.assertEqual(observation["result"], "passed")
            else:
                self.assertEqual(observation["result"], "failed")
                self.assertEqual(len(observation["git_calls"]), 2)
                self.assertEqual(observation["rest_calls"], [])

    def fixture(self):
        first, second = "a" * 40, "b" * 40
        return {"first": first, "second": second, "baseline": "c" * 40, "fetchedBase": "c" * 40,
            "provider_base": "c" * 40, "provider_base_absent_before_fetch": True,
            "git_calls": [{"command": "push", "target": commit + ":refs/heads/run-branch"}
                          for commit in (first, second)] + [{"command": "fetch",
                              "target": "refs/heads/develop:refs/heads/laomedo-read"}],
            "rest_calls": [{"method": "POST"}], "provider_commit": second,
            "provider_body": "checked", "finalBody": "checked", "checkoutClean": True,
            "agent_owned": True, "agent_alive": True,
            "push_effects": [{"state": "confirmed", "result_json": json.dumps({"commit": commit})}
                             for commit in (first, second)],
            "outcomes": [{"command": "git", "args": ["--force"], "status": 1},
                         {"command": "git", "args": ["HEAD:refs/heads/other"], "status": 1},
                         {"command": "git", "args": [], "status": 1},
                         {"command": "gh", "args": [], "status": 2},
                         {"command": "gh", "args": [], "status": 3}],
            "negative_controls": {"completed_push": "push_stage_unverified",
                "changed_connection": "connection_unavailable", "revoked_read": "grant_unavailable",
                "completed_freeze_error": "run_grant_mismatch", "completed_freeze_state": "unknown",
                "completed_freeze_created": False, "revoked_update": "grant_unavailable",
                "provider_count_unchanged": True}}

    def test_assessment_accepts_matching_synthetic_control(self):
        capture.validate_observation(self.fixture())
        values = self.fixture()
        for item in values["outcomes"][:3]:
            item["status"] = 128
        capture.validate_observation(values)

    def test_assessment_rejects_mutated_provider_and_command_observations(self):
        mutations = [lambda v: v["git_calls"].append(copy.deepcopy(v["git_calls"][0])),
                     lambda v: v["rest_calls"].append({"method": "POST"}),
                     lambda v: v.update(provider_commit="d" * 40),
                     lambda v: v.update(provider_body="unchecked"),
                     lambda v: v.update(agent_alive=False),
                     lambda v: v.update(provider_base_absent_before_fetch=False),
                     lambda v: v["git_calls"].pop(),
                     lambda v: v["outcomes"][0].update(status=0),
                     lambda v: v["push_effects"][1].update(state="unknown"),
                     lambda v: v["negative_controls"].update(completed_freeze_created=True),
                     lambda v: v["negative_controls"].update(revoked_update=None),
                     lambda v: v["negative_controls"].update(provider_count_unchanged=False)]
        for mutate in mutations:
            with self.subTest(mutation=mutations.index(mutate)):
                observation = self.fixture()
                mutate(observation)
                with self.assertRaises(ValueError):
                    capture.validate_observation(observation)
