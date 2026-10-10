"""Mutation controls of capture assessment, not campaign execution/evidence."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("native_capture", ROOT / "experiments/exp100/probe_native_capture.py")
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


class NativeCaptureChecks(unittest.TestCase):
    def fixture(self):
        first, second = "a" * 40, "b" * 40
        return {"first": first, "second": second, "baseline": "c" * 40, "fetchedBase": "c" * 40,
            "git_calls": [{"command": "push", "target": commit + ":refs/heads/run-branch"}
                          for commit in (first, second)],
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
                "provider_count_unchanged": True}}

    def test_assessment_accepts_matching_synthetic_control(self):
        capture.validate_observation(self.fixture())

    def test_assessment_rejects_mutated_provider_and_command_observations(self):
        mutations = [lambda v: v["git_calls"].append(copy.deepcopy(v["git_calls"][0])),
                     lambda v: v["rest_calls"].append({"method": "POST"}),
                     lambda v: v.update(provider_commit="d" * 40),
                     lambda v: v.update(provider_body="unchecked"),
                     lambda v: v.update(agent_alive=False),
                     lambda v: v["outcomes"][0].update(status=0),
                     lambda v: v["push_effects"][1].update(state="unknown"),
                     lambda v: v["negative_controls"].update(provider_count_unchanged=False)]
        for mutate in mutations:
            with self.subTest(mutation=mutations.index(mutate)):
                observation = self.fixture()
                mutate(observation)
                with self.assertRaises(ValueError):
                    capture.validate_observation(observation)
