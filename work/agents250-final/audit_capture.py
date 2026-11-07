"""Reconcile actual retained native records using current projections, no model call."""

import json
import subprocess
from collections import Counter
from pathlib import Path
from laomedo.agents.agents.opencode.history.models import NativeExport, NativeHistory
from laomedo.agents.agents.opencode.activity.models import OpenCodeTokenUsage
from laomedo.agents.agents.opencode.activity.projection import project


def main():
    e = Path("C:/CodeWorkspace/laomedo/claude-review.local/agents-250-20261107")
    state = Path(json.loads((e / "runtime-path.json").read_text())["path"])
    result = json.loads((e / "opencode-capture-final-run.json").read_text())
    root = state / "opencode/runs" / result["run_id"]
    record = json.loads((root / "record.json").read_text())
    rows = [
        json.loads(line)
        for line in (root / "activity-events.jsonl").read_text().splitlines()
    ]
    methods = Counter(row["event"]["method"] for row in rows)
    sessions, messages = {}, {}
    for row in rows:
        event = row["event"]
        params = event.get("params", {})
        if event["method"] == "opencode/sessionSnapshot":
            info = params["session"]
            sessions[info["id"]] = info
        if event["method"] == "opencode/messageSnapshot":
            messages[params["sessionID"]] = params["messages"]
    history = NativeHistory(
        root_id=record["thread_id"],
        sessions={
            key: NativeExport(info=info, messages=messages[key])
            for key, info in sessions.items()
        },
    )
    fields = history.record_fields(None)
    view = project(
        [{"raw": row["event"], "received_at": row["received_at"]} for row in rows],
        root_thread=record["thread_id"],
    )
    assert fields["answer"] == record["answer"]
    usage = (
        OpenCodeTokenUsage.from_native(fields["usage"]).to_activity_usage().to_payload()
    )
    assert usage == view["usage_by_thread"][record["thread_id"]]
    assert methods["acp/sessionUpdate"] > 0 and methods["item/agentMessage/delta"] > 0
    containers = subprocess.check_output(
        ["docker", "ps", "-a", "--format", "{{.Names}}"], text=True
    ).splitlines()
    pending_names = [
        name
        for name in containers
        if name.startswith(
            ("laomedo-oc-controller-", "laomedo-oc-worker-", "laomedo-oc-catalog-")
        )
    ]
    receipts = list((root / "docker-receipts").glob("*.json"))
    facts = {
        "source": "Current projection over immutable actual native receipts; no rerun or rewritten record",
        "run_id": result["run_id"],
        "methods": dict(methods),
        "answer_matches_native_record": True,
        "root_attempt_usage": fields["usage"],
        "root_usage_matches_activity": True,
        "previous_last_message_usage": record["usage"],
        "record_controller_cleanup": record.get("controller_cleanup"),
        "opencode_named_containers_present": len(pending_names),
        "run_receipt_count": len(receipts),
        "source_binding": "Real capture executed with7ca74370; current usage projection separately applied offline to that exact native data.",
    }
    (e / "actual-capture-reconciliation.json").write_text(
        json.dumps(facts, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "raw_updates": methods["acp/sessionUpdate"],
                "normalized_text_deltas": methods["item/agentMessage/delta"],
                "actual_root_usage_matches_activity": True,
                "opencode_containers_present": len(pending_names),
                "pending_run_receipts": len(receipts),
            }
        )
    )


if __name__ == "__main__":
    main()
