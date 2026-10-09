"""Single-use, credential-free recorded run of the S3 boundary controls."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from laomedo.github_git_transport import GitHubGitTransport
from laomedo.github_rest_transport import GitHubRestTransport
from laomedo.local_runner import LocalRunner


ROOT = Path(__file__).resolve().parents[2]
OBSERVATION = Path(__file__).with_name("observation-s3.json")
SOURCES = ("experiments/exp100/PROTOCOL-03.md",
           "experiments/exp100/AMENDMENT-04.md",
           "experiments/exp100/bundle_transfer.py",
           "experiments/exp100/handoff_s3.py",
           "experiments/exp100/test_handoff_s3.py")
REQUIRED_CASES = frozenset({
    "test_bound_bundle_is_imported_into_private_stage",
    "test_thin_bundle_requires_host_confirmed_stage",
    "test_wrong_branch_and_run_are_refused",
    "test_valid_bundle_from_another_run_cannot_bind_to_this_run",
    "test_wrong_baseline_truncated_and_malformed_leave_failure_records",
    "test_private_stage_must_be_disjoint_from_all_runner_mounts",
    "test_incomplete_prior_attempt_blocks_new_transfer",
    "test_divergent_later_commit_is_not_accepted_as_fast_forward",
    "test_windows_reparse_attribute_is_refused_even_for_regular_file",
    "test_replacement_detected_after_open_is_not_staged",
    "test_hardlink_and_oversize_are_refused_before_git",
    "test_workflow_change_and_extra_ref_never_reach_stage",
    "test_agent_hook_and_hostile_remote_are_not_used",
    "test_host_git_guard_rejects_agent_repository_and_local_git_still_works",
    "test_symlink_handoff_is_refused_where_supported",
    "test_windows_junction_handoff_is_refused",
})


class CaseResult(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.rows = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.rows.append({"case": test._testMethodName, "status": "passed"})

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.rows.append({"case": test._testMethodName,
                          "status": "skipped", "reason": reason})

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.rows.append({"case": test._testMethodName,
                          "status": "failed", "error_class": err[0].__name__})

    def addError(self, test, err):
        super().addError(test, err)
        self.rows.append({"case": test._testMethodName,
                          "status": "error", "error_class": err[0].__name__})


def run() -> dict:
    version = subprocess.run(["git", "--version"], capture_output=True,
                             text=True, timeout=10, check=True).stdout.strip()
    checks = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
              for name in SOURCES}
    source_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                   capture_output=True, text=True, timeout=10,
                                   check=True).stdout.strip()
    suite = unittest.defaultTestLoader.loadTestsFromName(
        "experiments.exp100.test_handoff_s3.HandoffS3Tests")
    s2_suite = unittest.defaultTestLoader.loadTestsFromName(
        "experiments.exp100.test_bundle_transfer")
    result = CaseResult()
    s2_result = CaseResult()
    provider_calls = []
    model_turns = []

    def forbid_provider(*args, **kwargs):
        provider_calls.append("forbidden")
        raise AssertionError("provider call forbidden in S3")

    def forbid_model(*args, **kwargs):
        model_turns.append("forbidden")
        raise AssertionError("model turn forbidden in S3")

    with patch.object(GitHubGitTransport, "__call__", side_effect=forbid_provider), \
            patch.object(GitHubRestTransport, "__call__", side_effect=forbid_provider), \
            patch.object(LocalRunner, "start", side_effect=forbid_model):
        suite.run(result)
        s2_suite.run(s2_result)
    rows = sorted(result.rows, key=lambda row: row["case"])
    s2_rows = sorted(s2_result.rows, key=lambda row: row["case"])
    statuses = {row["case"]: row["status"] for row in rows}
    passed = not (set(statuses) != REQUIRED_CASES or
            any(statuses[name] != "passed" for name in REQUIRED_CASES - {
                "test_symlink_handoff_is_refused_where_supported",
                "test_windows_junction_handoff_is_refused"}) or
            not any(statuses[name] == "passed" for name in (
                "test_symlink_handoff_is_refused_where_supported",
                "test_windows_junction_handoff_is_refused")) or
            provider_calls or model_turns or not s2_rows or
            any(row["status"] != "passed" for row in s2_rows))
    return {"schema_version": 1, "identity": "EXP-100-S3-01",
            "status": "passed" if passed else "failed",
            "source_commit": source_commit,
            "git_version": version, "source_sha256": checks,
            "cases": rows, "reused_s2_case_results": s2_rows,
            "provider_transport_calls": len(provider_calls),
            "model_turn_attempts": len(model_turns),
            "reused_s2_controls": [
                "missing_object_integrity", "bundle_filter_and_object_format",
                "host_global_config_isolation", "hostile_remote_and_hook_nonuse"],
            "new_s3_controls": sorted(REQUIRED_CASES),
            "provider_count_scope": "instrumented Git/REST transport entrypoints",
            "model_count_scope": "instrumented LocalRunner.start entrypoint",
            "actual_git_or_gh_remote_calls": "not independently packet-captured"}


def record_once(path: Path, source_commit: str, run_probe=run) -> dict:
    """Consume the evidence identity before running, including on failure."""
    with path.open("x", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps({"identity": "EXP-100-S3-01", "status": "unknown",
                                 "source_commit": source_commit}) + "\n")
        output.flush()
        os.fsync(output.fileno())
    try:
        observation = run_probe()
    except Exception as error:
        observation = {"schema_version": 1, "identity": "EXP-100-S3-01",
                       "status": "failed", "source_commit": source_commit,
                       "error_class": type(error).__name__, "cases": []}
    pending = path.with_suffix(".pending")
    with pending.open("x", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(observation, indent=2, sort_keys=True) + "\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(pending, path)
    return observation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args()
    if args.record:
        if OBSERVATION.exists():
            raise SystemExit("S3 identity already recorded; no automatic retry")
        status = subprocess.run(["git", "status", "--porcelain=v1",
                                 "--untracked-files=all"], cwd=ROOT,
                                capture_output=True, text=True, timeout=10, check=True)
        if status.stdout:
            raise SystemExit("source tree must be clean before recording")
    if args.record:
        source_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                       capture_output=True, text=True,
                                       timeout=10, check=True).stdout.strip()
        observation = record_once(OBSERVATION, source_commit)
    else:
        observation = run()
        print(json.dumps(observation, indent=2, sort_keys=True))
    if observation.get("status") != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
