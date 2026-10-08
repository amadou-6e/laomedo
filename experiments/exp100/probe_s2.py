"""Single-use, credential-free EXP-100/S2 observation writer.

Development test runs are not evidence. Only --record creates the pinned
observation; it refuses to replace an existing evidence file.
"""

from __future__ import annotations

import argparse
import json
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
    ("test_extra_ref_and_truncated_pack_are_not_accepted", ("R1", "V1"),
     ("ref_count", "object_invalid")),
    ("test_unrelated_history_and_workflow_diff", ("H1", "W1"),
     ("baseline_ancestry", "workflow_change")),
    ("test_bundle_capabilities_and_tag_object",
     ("A1-cap-control", "F1", "O1", "F1-control", "R3"),
     ("accepted", "bundle_version", "object_format", "accepted", "ref_type")),
    ("test_complete_pack_with_missing_object_is_rejected_at_integrity", ("I1",),
     ("object_invalid",)),
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
    for method, ids, expected in CASE_METHODS:
        case = BundleTransferTests(method)
        try:
            case.setUp()
            case.capture = []
            getattr(case, method)()
            if len(case.capture) != len(ids):
                raise AssertionError(f"{method}: recorded {len(case.capture)} != {len(ids)}")
            for identifier, want, result in zip(ids, expected, case.capture):
                if result["reason"] != want:
                    raise AssertionError(f"{identifier}: {result['reason']} != {want}")
                rows.append({"id": identifier, "expected_reason": want, **result})
        finally:
            case.doCleanups()
        if time.monotonic() - started > 120:
            raise RuntimeError("protocol_total_timeout")
    return {"schema": "exp100-s2-observation-v1", "git_version": git_version,
            "protocol_head": "e1c954b", "provider_calls": 0,
            "model_turns": 0, "status": "passed_local_cases",
            "cases": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args()
    observation = run_once()
    encoded = json.dumps(observation, indent=2, sort_keys=True) + "\n"
    target = Path(__file__).with_name("observation-s2.json")
    if args.record:
        with target.open("x", encoding="utf-8", newline="\n") as output:
            output.write(encoded)
        print(f"recorded {len(observation['cases'])} cases")
    elif target.exists():
        if target.read_text(encoding="utf-8") != encoded:
            raise RuntimeError("recorded_observation_changed")
        print(f"reproduced {len(observation['cases'])} cases")
    else:
        print(f"dry run: {len(observation['cases'])} cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
