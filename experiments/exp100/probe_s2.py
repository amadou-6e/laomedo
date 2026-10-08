"""Single-use, credential-free EXP-100/S2 observation writer.

Development test runs are not evidence. Only --record creates the pinned
observation; it refuses to replace an existing evidence file.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from tests.test_exp100_bundle_transfer import BundleTransferTests


CASE_METHODS = (
    ("test_first_commit_import_and_exact_ref", ("A1", "R2"),
     ("accepted", "ref_name")),
    ("test_second_commit_requires_host_confirmed_seed", ("A1-seed", "M1", "A2"),
     ("accepted", "missing_prerequisite", "accepted")),
    ("test_extra_ref_and_truncated_pack_are_not_accepted",
     ("R1", "V1-control", "V1"),
     ("ref_count", "accepted", "object_invalid")),
    ("test_unrelated_history_and_workflow_diff", ("H1", "W1"),
     ("baseline_ancestry", "workflow_change")),
    ("test_bundle_capabilities_and_tag_object",
     ("A1-cap-control", "F1", "O1", "F1-control", "R3"),
     ("accepted", "bundle_version", "object_format", "accepted", "ref_type")),
    ("test_complete_pack_with_missing_object_is_rejected_at_integrity",
     ("I1-control", "I1"), ("accepted", "object_invalid")),
    ("test_agent_hook_detector_fires_only_in_agent", ("ISO-hook",),
     ("accepted",)),
    ("test_host_global_and_inherited_trace_controls", ("ISO-config",),
     ("accepted",)),
    ("test_host_never_contacts_agent_remote", ("ISO-remote",),
     ("accepted",)),
    ("test_post_export_agent_alternates_and_replace_refs_do_not_change_stage",
     ("ISO-replace-before", "ISO-replace-after"),
     ("accepted", "accepted")),
)


def run_once() -> dict:
    started = time.monotonic()
    git_version = subprocess.run(["git", "--version"], check=True,
                                 capture_output=True, text=True, timeout=10).stdout.strip()
    rows = []
    failed = False
    for method, ids, expected in CASE_METHODS:
        case = BundleTransferTests(method)
        try:
            case.setUp()
            case.capture = []
            getattr(case, method)()
            if len(case.capture) != len(ids):
                failed = True
            for identifier, want, result in zip(ids, expected, case.capture):
                if result["reason"] != want:
                    failed = True
                rows.append({"id": identifier, "expected_reason": want,
                             "case_status": ("passed" if result["reason"] == want
                                             else "failed"), **result})
            for identifier, want in zip(ids[len(case.capture):], expected[len(case.capture):]):
                rows.append({"id": identifier, "expected_reason": want,
                             "case_status": "failed", "reason": "not_reached",
                             "stage": "method",
                             "commit": None, "tree": None, "bundle_sha256": None})
        except Exception as error:
            failed = True
            captured = getattr(case, "capture", None) or []
            for identifier, want, result in zip(ids, expected, captured):
                rows.append({"id": identifier, "expected_reason": want,
                             "case_status": "failed",
                             "failure_type": type(error).__name__, **result})
            for identifier, want in zip(ids[len(captured):], expected[len(captured):]):
                rows.append({"id": identifier, "expected_reason": want,
                             "case_status": "failed",
                             "reason": "not_reached", "stage": type(error).__name__,
                             "commit": None, "tree": None, "bundle_sha256": None})
        finally:
            case.doCleanups()
        if time.monotonic() - started > 120:
            failed = True
            break
    return {"schema": "exp100-s2-observation-v1", "git_version": git_version,
            "protocol_head": "e1c954b", "provider_calls": 0,
            "model_turns": 0, "status": "failed" if failed else "passed_local_cases",
            "cases": rows}


def record_once(target: Path, source: str, run=run_once) -> dict:
    """Reserve the evidence identity before any case and preserve failures."""
    with target.open("x", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps({"status": "reserved", "source_head": source}) + "\n")
    try:
        observation = run()
        observation["source_head"] = source
    except BaseException as error:
        observation = {"schema": "exp100-s2-observation-v1",
                       "status": "failed", "source_head": source,
                       "error_type": type(error).__name__, "cases": []}
    pending = target.with_suffix(".pending")
    with pending.open("x", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(observation, indent=2, sort_keys=True) + "\n")
    os.replace(pending, target)
    return observation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args()
    target = Path(__file__).with_name("observation-s2.json")
    if args.record:
        source = subprocess.run(["git", "rev-parse", "HEAD"], check=True,
                                capture_output=True, text=True, timeout=10).stdout.strip()
        dirt = subprocess.run(["git", "status", "--porcelain"], check=True,
                              capture_output=True, text=True, timeout=10).stdout
        if dirt:
            raise RuntimeError("source_tree_not_clean")
        observation = record_once(target, source)
        print(f"recorded {len(observation['cases'])} cases: {observation['status']}")
        return 0 if observation["status"] == "passed_local_cases" else 1
    observation = run_once()
    if target.exists():
        recorded = json.loads(target.read_text(encoding="utf-8"))
        observation["source_head"] = recorded.get("source_head")
        if recorded != observation:
            raise RuntimeError("recorded_observation_changed")
        print(f"reproduced {len(observation['cases'])} cases")
    else:
        print(f"dry run: {len(observation['cases'])} cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
