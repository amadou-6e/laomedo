"""Export bounded AMENDMENT-07 facts without answers, tool text or credentials."""
from hashlib import sha256
import json
from pathlib import Path
import socket
import sqlite3
from laomedo.agents.contracts.output import evaluate_envelope; from laomedo.agents.contracts.output import requirements
from laomedo.host.credentials.siwc.utils import _outside_git

RUN = "f1db640f-9f02-4655-88b8-76b1bd467f24"


def observe(root):
    root = _outside_git(root)
    activation = json.loads((root / "activation.json").read_bytes())
    ledger = json.loads((root / "runner/turn-ledger.json").read_bytes())
    assert ledger == {"attempted_turns": 7, "max_authorized_turns": 10}
    record_path = root / "runner/runs" / RUN / "record.json"
    record = json.loads(record_path.read_bytes())
    flow = json.loads((root / "flow-input/success.json").read_bytes())
    submission = json.loads(record["answer"])
    envelope = {"schema_version": "laomedo.agent-submission.v1",
        "submission": submission,
        "requirements_revision": record["requirements_revision"],
        "task_outcome": submission.get("task_outcome", "unknown"), "executor_status": record["status"]}
    forms = {}
    for node in flow["data"]["nodes"]:
        if node["id"] in {"requirements", "contract"}:
            form = requirements(json.loads(node["data"]["node"]["template"]["requirements_json"]["value"]))
            checked = evaluate_envelope(form, envelope)
            forms[node["id"]] = {"status": checked["contract_status"],
                "error_codes": [error["code"] for error in checked["errors"]]}
    with sqlite3.connect("file:" + (root / "host/write-budget.sqlite").as_posix() + "?mode=ro", uri=True) as db:
        writes = [row[0] for row in db.execute("SELECT operation FROM attempts ORDER BY operation")]
    with sqlite3.connect("file:" + (root / "host/mediator/mediator.sqlite").as_posix() + "?mode=ro", uri=True) as db:
        phase = db.execute("SELECT phase FROM publication_handoffs WHERE run_id=?", (RUN,)).fetchone()[0]
        active = db.execute("SELECT COUNT(*) FROM grants WHERE revoked_at IS NULL").fetchone()[0]
        effects = [{"operation": operation, "state": state} for operation, state in
                   db.execute("SELECT operation,state FROM effects WHERE run_id=?", (RUN,))]
    with socket.socket() as probe:
        probe.settimeout(1)
        listening = probe.connect_ex(("127.0.0.1", 8779)) == 0
    graph = json.loads((root / "amend07-success.json").read_bytes())
    readback = json.loads((root / "amend07-branch-readback.json").read_bytes())
    assert writes == ["git_push"] and readback["matching_pr_count"] == 0
    report = record_path.parent / "post-run/experiments/exp139/issue-report.md"
    commands = []
    for line in (record_path.parent / "raw-events.jsonl").read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        item = event.get("params", {}).get("item", {})
        if event.get("method") == "item/completed" and item.get("type") == "commandExecution":
            code = item.get("exitCode")
            commands.append({"exit_code": code if type(code) is int else "unknown"})
    return {"experiment": "EXP-139", "result": "blocked_no_go",
        "execution_source": activation["source_sha"], "manifest_sha256": activation["manifest_sha256"],
        "ledger": ledger, "run_id": RUN, "status": record["status"],
        "evidence_complete": record["evidence_complete"], "completion_basis": record["completion_basis"],
        "closure": {key: record.get("evidence_closure", {}).get(key)
                    for key in ("version", "reason", "item_count", "turn_count")},
        "precheck": {key: record.get("precheck", {}).get(key) for key in ("installed", "call_count")},
        "graph_result": graph["graph_result"], "retained_result_contract_recheck": forms,
        "recheck_executor_status_basis": "retained_final_record",
        "commands": commands,
        "exact_report_bytes": sha256(report.read_bytes()).hexdigest() == readback["report_sha256"],
        "branch_readback": readback, "write_attempts": writes, "effects": effects,
        "publication_phase": phase, "draft_pr": None, "active_github_grants": active,
        "recorded_handoff_phase": record.get("publication_handoff", {}).get("phase")
            if record.get("publication_handoff", {}).get("phase") in {"validation_pending", "expired"} else "unknown",
        "runner_listening": listening,
        "cleanup_verified": record.get("container_ownership", {}).get("cleanup_verified"),
        "controller_cleanup": record.get("controller_cleanup"),
        "graph_finished_before_terminal_record_by_mtime": graph["state"] == "finished" and
            (root / "amend07-success.json").stat().st_mtime < record_path.stat().st_mtime,
        "blocker": "downstream_rejection_before_terminal_runner_result",
        "cause": "unproven; original graph summary did not preserve diagnostic codes",
        "scope": "bounded_single_user_local_only"}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    result = observe(parser.parse_args().state.resolve())
    Path(__file__).with_name("AMEND07-OBSERVATION.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in
        ("result", "ledger", "publication_phase", "write_attempts", "active_github_grants", "runner_listening")}))
