"""EXP-15 bounded live GitHub issue reconciliation probe.

Requires external authorization. The target is hard-coded to a disposable repo.
There is no cleanup and no retry after an uncertain POST.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from uuid import uuid4


REPOSITORY = "amadou-6e/laomedo-exp15-disposable"
API_VERSION = "X-GitHub-Api-Version: 2022-11-28"
SCHEDULE_SECONDS = (0, 1, 2, 3, 5, 8, 13, 21, 30, 42, 60)


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".exp15-", dir=path.parent)
    pending = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(record, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def api(*args):
    result = subprocess.run(["gh", "api", "-H", API_VERSION, *args],
                            capture_output=True, text=True, check=True, timeout=30)
    return json.loads(result.stdout)


def marker_of(body):
    for line in (body or "").splitlines():
        if line.startswith("EXP15-MARKER: "):
            return line.removeprefix("EXP15-MARKER: ")
    return None


def exact_matches(items, marker):
    return sorted([{"number": item["number"], "id": item["id"]}
                   for item in items if "pull_request" not in item
                   and marker_of(item.get("body")) == marker],
                  key=lambda item: item["number"])


def observe(marker):
    listed = api("-X", "GET", f"repos/{REPOSITORY}/issues",
                 "-f", "state=all", "-f", "per_page=100", "-f", "page=1")
    if len(listed) == 100:
        raise RuntimeError("list pagination required; cannot claim absence")
    searched = api("-X", "GET", "search/issues", "-f",
                   f"q=repo:{REPOSITORY} is:issue in:body {marker}",
                   "-f", "per_page=100")
    return {"at": now(), "list_matches": exact_matches(listed, marker),
            "search_matches": exact_matches(searched["items"], marker),
            "search_total_count": searched["total_count"],
            "search_incomplete": searched["incomplete_results"]}


def create(title, marker, suppress_ack=False):
    command = ["gh", "api", "-H", API_VERSION, "-X", "POST",
               f"repos/{REPOSITORY}/issues", "-f", f"title={title}",
               "-f", "body=Disposable EXP-15 test issue. Do not use for work.\n\n"
                     f"EXP15-MARKER: {marker}"]
    if suppress_ack:
        # Caller sees neither status nor response. This does not simulate a
        # network partition: it deliberately suppresses acknowledgement.
        subprocess.run(command, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=False, timeout=30)
        return None
    result = subprocess.run(command, capture_output=True, text=True,
                            check=True, timeout=30)
    item = json.loads(result.stdout)
    return {"number": item["number"], "id": item["id"]}


def run(path):
    if path.exists():
        raise FileExistsError("evidence exists; never repeat an attempted POST")
    run_id = uuid4().hex
    marker = f"exp15-{run_id}"
    record = {"run_id": run_id, "repository": REPOSITORY,
              "started_at": now(), "marker": marker,
              "api_version": "2022-11-28", "phase": "prepared",
              "method": "response-suppressed POST then read-only list/search; no retry",
              "duplicate_post_attempts": 0, "observations": [],
              "created_controls": []}
    save(path, record)
    record["phase"] = "suppressed_post_attempted"
    save(path, record)  # Crash here makes the outcome unknown.
    create(f"EXP-15 suppressed acknowledgement {run_id}", marker, True)
    started = time.monotonic()
    for target in SCHEDULE_SECONDS:
        time.sleep(max(0, started + target - time.monotonic()))
        entry = observe(marker)
        entry["elapsed_seconds"] = round(time.monotonic() - started, 3)
        record["observations"].append(entry)
        save(path, record)
    for kind, control_marker in (
        ("acknowledged", f"exp15-control-{run_id}"),
        ("near_collision", f"exp15-{run_id}x"),
    ):
        record["phase"] = f"{kind}_post_attempted"
        save(path, record)
        result = create(f"EXP-15 {kind} {run_id}", control_marker)
        record["created_controls"].append(
            {"kind": kind, "marker": control_marker, **result})
        save(path, record)
    record["phase"] = "complete"
    record["completed_at"] = now()
    record["final_observation"] = observe(marker)
    save(path, record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()
    if not args.execute:
        parser.error("live writes require --execute and external authorization")
    run(args.evidence)


if __name__ == "__main__":
    main()
