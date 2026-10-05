"""Falsifying checks for the direct-capture EXP-66 live synthetic trace."""

from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import unittest


OBSERVATION = Path(__file__).resolve().parents[1] / "experiments/exp66/observation.json"
KINDS = ["invocation_reserved", "dispatch_started", "caller_timeout",
         "native_job_observed", "native_job_observed",
         "external_effect_observed", "native_job_observed", "native_job_observed"]


def check_observation(report):
    config = report["config"]
    if (config["effective_server_timeout_seconds"] != 3 or
            config["poll_offsets_seconds"] != [0, 1, 4, 7]):
        raise AssertionError("frozen runtime configuration changed")
    caller = report["caller"]
    if (caller.get("status") != 408 or
            caller.get("response", {}).get("code") != "EXECUTION_TIMEOUT" or
            not caller["response"].get("job_id")):
        raise AssertionError("timeout identity missing")
    polls = report["status_snapshots"]
    if ([row["target_offset_seconds"] for row in polls] != [0, 1, 4, 7] or
            any(row.get("http_status") != 500 or row.get("detail_code") != "JOB_FAILED"
                for row in polls)):
        raise AssertionError("native job observations differ")
    events = report["runner_events"]
    if [row["event"] for row in events] != ["entered", "effect", "response_written"]:
        raise AssertionError("single runner effect evidence missing")
    clock = report["clock_before"]
    if abs(clock["estimated_offset_seconds"]) > 1 or clock["uncertainty_seconds"] > 0.5:
        raise AssertionError("clock calibration insufficient")
    effect_host_time = datetime.fromisoformat(events[1]["utc"]) - timedelta(
        seconds=clock["estimated_offset_seconds"])
    caller_end = datetime.fromisoformat(caller["started_utc"]) + timedelta(
        seconds=caller["duration_seconds"])
    if (effect_host_time - caller_end).total_seconds() <= 2:
        raise AssertionError("effect did not follow timeout")
    if not (datetime.fromisoformat(polls[1]["observed_utc"]) < effect_host_time <
            datetime.fromisoformat(polls[2]["observed_utc"])):
        raise AssertionError("job-failed/effect ordering unsupported")

    before = report["trace_before_reopen"]
    after = report["trace_after_reopen"]
    if before != after or report["restart_sweep_ids"]:
        raise AssertionError("durable trace changed on reopen")
    invocation = after["invocation"]
    if (after["run_status"] != "timed_out" or after["dispatch_attempts"] != 1 or
            after["stream_state"] != "partial" or after["evidence_complete"] or
            invocation["status"] != "failed" or
            invocation["evidence_state"] != "partial" or
            invocation["effect_state"] != "observed" or
            invocation["native_job_state"] != "failed" or
            invocation["native_job_id"] != caller["response"]["job_id"]):
        raise AssertionError("partial timeout projection misreported")
    if after["action_uniqueness"] != "uncertain" or "unique_action_count" in after:
        raise AssertionError("unverified action uniqueness claimed")
    receipts = after["receipts"]
    if [row["kind"] for row in receipts] != KINDS or after["event_count"] != 8:
        raise AssertionError("trace receipts missing or reordered")
    if not (datetime.fromisoformat(receipts[0]["received_at"].replace("Z", "+00:00")) <
            datetime.fromisoformat(receipts[1]["received_at"].replace("Z", "+00:00")) <
            datetime.fromisoformat(caller["started_utc"])):
        raise AssertionError("identity/dispatch not saved before native call")
    if receipts[5]["source_time"] != events[1]["utc"]:
        raise AssertionError("effect source time not retained")
    digest = sha256(json.dumps(events[1], sort_keys=True).encode("utf-8")).hexdigest()
    if receipts[5]["payload"].get("source_ref") != "sha256:" + digest:
        raise AssertionError("effect source hash mismatch")
    if any("cancelled" in json.dumps(row).lower() for row in receipts):
        raise AssertionError("unverified cancellation claimed")


class LiveSyntheticTraceTests(unittest.TestCase):
    def setUp(self):
        self.report = json.loads(OBSERVATION.read_text(encoding="utf-8"))

    def test_committed_observation(self):
        check_observation(self.report)
        self.assertNotIn("synthetic-exp10-token", OBSERVATION.read_text(encoding="utf-8"))

    def test_omitted_effect_is_rejected(self):
        changed = deepcopy(self.report)
        changed["trace_after_reopen"]["receipts"].pop(5)
        with self.assertRaisesRegex(AssertionError, "durable trace changed"):
            check_observation(changed)

    def test_fabricated_complete_or_cancelled_is_rejected(self):
        for field, value in (("stream_state", "complete"), ("run_status", "cancelled")):
            with self.subTest(field=field):
                changed = deepcopy(self.report)
                changed["trace_before_reopen"][field] = value
                changed["trace_after_reopen"][field] = value
                with self.assertRaisesRegex(AssertionError, "partial timeout projection"):
                    check_observation(changed)

    def test_job_failed_code_is_required(self):
        changed = deepcopy(self.report)
        changed["status_snapshots"][0]["detail_code"] = "INTERNAL_SERVER_ERROR"
        with self.assertRaisesRegex(AssertionError, "native job observations"):
            check_observation(changed)

    def test_effect_source_tamper_is_rejected(self):
        changed = deepcopy(self.report)
        changed["runner_events"][1]["monotonic"] += 1
        with self.assertRaisesRegex(AssertionError, "effect source hash"):
            check_observation(changed)


if __name__ == "__main__":
    unittest.main()
