"""Independent checks of EXP-10's pinned synthetic timeout observation."""

from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
import unittest


OBSERVATION = Path(__file__).with_name("observation.json")


def check_observation(report: dict) -> None:
    cases = report["cases"]
    if [case["case"] for case in cases] != ["control", "client", "component", "server"]:
        raise AssertionError("frozen case set changed")
    if report["config"]["server_timeout_seconds"] != 3:
        raise AssertionError("effective server timeout not verified")
    expected = {
        "control": ("response", 200, False),
        "client": ("client_error", None, True),
        "component": ("http_error", 500, False),
        "server": ("http_error", 408, True),
    }
    for case in cases:
        name = case["case"]
        kind, status, after = expected[name]
        if case["kind"] != kind or case.get("status") != status:
            raise AssertionError(f"{name}: unexpected caller outcome")
        events = case["runner_events"]
        if [event["event"] for event in events[:2]] != ["entered", "effect"]:
            raise AssertionError(f"{name}: missing entry/effect evidence")
        if sum(event["event"] == "entered" for event in events) != 1 or sum(
                event["event"] == "effect" for event in events) != 1:
            raise AssertionError(f"{name}: duplicate or absent synthetic action")
        if not case["effect_observed"]:
            raise AssertionError(f"{name}: effect wrongly marked absent")
        started = datetime.fromisoformat(case["started_utc"])
        caller_end = started + timedelta(seconds=case["duration_seconds"])
        effect = datetime.fromisoformat(events[1]["utc"])
        if (effect > caller_end) != case["effect_after_caller"]:
            raise AssertionError(f"{name}: effect/caller ordering misreported")
        if case["effect_after_caller"] != after:
            raise AssertionError(f"{name}: timeout/effect ordering differs")
        if case["duration_seconds"] > case["configured_caller_timeout_seconds"] + 1:
            raise AssertionError(f"{name}: caller exceeded its bounded wait")
    if cases[0]["response"]["answer"] != "synthetic-effect":
        raise AssertionError("control did not return synthetic success")
    if cases[1].get("error_type") != "TimeoutError":
        raise AssertionError("outer caller did not time out")
    if "remote execution may still be active" not in cases[2]["response"]["message"]:
        raise AssertionError("component hid uncertain remote effect")
    if (cases[3]["response"].get("code") != "EXECUTION_TIMEOUT" or
            not cases[3]["response"].get("job_id")):
        raise AssertionError("server timeout lacked status/job evidence")


class TimeoutObservationTests(unittest.TestCase):
    def setUp(self):
        self.report = json.loads(OBSERVATION.read_text(encoding="utf-8"))

    def test_frozen_observation(self):
        check_observation(self.report)
        self.assertNotIn("synthetic-exp10-token", OBSERVATION.read_text(encoding="utf-8"))

    def test_missing_late_effect_is_detected(self):
        changed = deepcopy(self.report)
        changed["cases"][1]["runner_events"] = changed["cases"][1]["runner_events"][:1]
        with self.assertRaisesRegex(AssertionError, "missing entry/effect"):
            check_observation(changed)

    def test_fabricated_timeout_safety_is_detected(self):
        changed = deepcopy(self.report)
        changed["cases"][3]["effect_after_caller"] = False
        with self.assertRaisesRegex(AssertionError, "ordering misreported"):
            check_observation(changed)

    def test_late_success_cannot_be_called_timely(self):
        changed = deepcopy(self.report)
        changed["cases"][3]["kind"] = "response"
        changed["cases"][3]["status"] = 200
        with self.assertRaisesRegex(AssertionError, "unexpected caller outcome"):
            check_observation(changed)


if __name__ == "__main__":
    unittest.main()
