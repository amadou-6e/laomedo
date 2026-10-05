"""Checks that the pinned post-408 observation cannot hide a late effect."""

from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
import unittest


OBSERVATION = Path(__file__).with_name("observation.json")


def check_observation(report: dict) -> None:
    if report["config"]["server_timeout_seconds"] != 3:
        raise AssertionError("effective server timeout not verified")
    if report["config"]["poll_offsets_seconds"] != [0, 1, 4, 7]:
        raise AssertionError("poll schedule changed")
    caller = report["caller"]
    if caller.get("status") != 408 or caller.get("response", {}).get("code") != "EXECUTION_TIMEOUT":
        raise AssertionError("server timeout response missing")
    job_id = caller["response"].get("job_id")
    if not job_id:
        raise AssertionError("job identity missing")
    if not 2.5 <= caller["duration_seconds"] <= 4:
        raise AssertionError("server timeout duration unexpected")
    events = report["runner_events"]
    if [row["event"] for row in events] != ["entered", "effect", "response_written"]:
        raise AssertionError("runner entry/effect evidence missing or duplicated")
    clock = report["clock_before"]
    if abs(clock["estimated_offset_seconds"]) > 1 or clock["uncertainty_seconds"] > 0.5:
        raise AssertionError("host/container clock calibration inadequate")
    caller_end = datetime.fromisoformat(caller["started_utc"]) + timedelta(
        seconds=caller["duration_seconds"])
    effect_host_time = datetime.fromisoformat(events[1]["utc"]) - timedelta(
        seconds=clock["estimated_offset_seconds"])
    if (effect_host_time - caller_end).total_seconds() <= 2:
        raise AssertionError("late effect not established")
    snapshots = report["status_snapshots"]
    if [row["target_offset_seconds"] for row in snapshots] != [0, 1, 4, 7]:
        raise AssertionError("status observations missing")
    if any(row.get("http_status") != 500 or row.get("detail_code") != "JOB_FAILED"
           for row in snapshots):
        raise AssertionError("job failure status misreported")
    if any(row.get("error_detail_present") for row in snapshots):
        raise AssertionError("unexpected durable failure detail")
    first_poll = datetime.fromisoformat(snapshots[0]["observed_utc"])
    if first_poll >= datetime.fromisoformat(events[1]["utc"]):
        raise AssertionError("job failure was not observed before effect")
    if any("cancelled" in json.dumps(row).lower() or "completed" in json.dumps(row).lower()
           for row in snapshots):
        raise AssertionError("unverified cancellation/completion claim")


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.report = json.loads(OBSERVATION.read_text(encoding="utf-8"))

    def test_pinned_observation(self):
        check_observation(self.report)
        self.assertNotIn("synthetic-exp10-token", OBSERVATION.read_text(encoding="utf-8"))

    def test_omitted_late_effect_is_rejected(self):
        changed = deepcopy(self.report)
        changed["runner_events"] = changed["runner_events"][:1]
        with self.assertRaisesRegex(AssertionError, "entry/effect"):
            check_observation(changed)

    def test_fabricated_safe_job_status_is_rejected(self):
        changed = deepcopy(self.report)
        changed["status_snapshots"][0]["detail_code"] = "CANCELLED"
        with self.assertRaisesRegex(AssertionError, "job failure status"):
            check_observation(changed)

    def test_effect_before_timeout_is_rejected(self):
        changed = deepcopy(self.report)
        changed["runner_events"][1]["utc"] = changed["caller"]["started_utc"]
        with self.assertRaisesRegex(AssertionError, "late effect"):
            check_observation(changed)


if __name__ == "__main__":
    unittest.main()
