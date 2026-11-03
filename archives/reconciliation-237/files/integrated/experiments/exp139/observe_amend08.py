"""Export bounded live acceptance evidence, excluding transcript and credential content."""

from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import socket
import sqlite3
from laomedo.agents.interface.output.utils import precheck_response
from laomedo.host.credentials.siwc.utils import _outside_git


def observe(root):
    root = _outside_git(root)
    activation = json.loads((root / "activation.json").read_bytes())
    config = json.loads((root / "config.json").read_bytes())
    ledger = json.loads((root / "runner/turn-ledger.json").read_bytes())
    assert ledger == {"attempted_turns": 8, "max_authorized_turns": 10}
    readback = json.loads((root / "readback.json").read_bytes())
    run_id = readback["run_id"]
    directory = root / "runner/runs" / run_id
    record = json.loads((directory / "record.json").read_bytes())
    graph = json.loads((root / "amend08-success.json").read_bytes())
    assert graph["graph_result"] == [
        {
            "outcomes": [
                {
                    "phase": "completed",
                    "publication_state": "confirmed",
                    "run_id": run_id,
                }
            ]
        }
    ]
    assert record["status"] == "completed" and record["evidence_complete"] is True
    assert record["container_ownership"]["cleanup_verified"] is True
    assert record["controller_cleanup"] == "confirmed"
    report = directory / "post-run/experiments/exp139/issue-report.md"
    assert (
        sha256(report.read_bytes()).hexdigest()
        == config["report_sha256"]
        == readback["published_report_sha256"]
    )
    assert (
        readback["draft"] is True and readback["only_expected_report_changed"] is True
    )
    assert readback["published_current_credential_matches"] is False
    commands, checks = [], []
    for line in (
        (directory / "raw-events.jsonl").read_text(encoding="utf-8").splitlines()
    ):
        event = json.loads(line)
        if event.get("method") == "item/tool/call":
            response = precheck_response(
                record["output_requirements"], event["params"], record["thread_id"]
            )
            check = json.loads(response["contentItems"][0]["text"])
            checks.append(
                {
                    "status": check["contract_status"],
                    "codes": [error["code"] for error in check["errors"]],
                }
            )
        item = event.get("params", {}).get("item", {})
        if (
            event.get("method") == "item/completed"
            and item.get("type") == "commandExecution"
        ):
            code = item.get("exitCode")
            commands.append({"exit_code": code if type(code) is int else "unknown"})
    with closing(
        sqlite3.connect(
            "file:" + Path(config["prior_write_budget"]).as_posix() + "?mode=ro",
            uri=True,
        )
    ) as db:
        previous = [
            r[0]
            for r in db.execute("SELECT operation FROM attempts ORDER BY operation")
        ]
    with closing(
        sqlite3.connect(
            "file:" + (root / "host/write-budget.sqlite").as_posix() + "?mode=ro",
            uri=True,
        )
    ) as db:
        writes = [
            r[0]
            for r in db.execute("SELECT operation FROM attempts ORDER BY operation")
        ]
    assert previous == ["git_push"] and writes == ["git_push", "pr_create"]
    with closing(
        sqlite3.connect(
            "file:" + (root / "host/mediator/mediator.sqlite").as_posix() + "?mode=ro",
            uri=True,
        )
    ) as db:
        active = db.execute(
            "SELECT COUNT(*) FROM grants WHERE revoked_at IS NULL"
        ).fetchone()[0]
        phase = db.execute(
            "SELECT phase FROM publication_handoffs WHERE run_id=?", (run_id,)
        ).fetchone()[0]
        effects = [
            {"operation": operation, "state": state}
            for operation, state in db.execute(
                "SELECT operation,state FROM effects WHERE run_id=? ORDER BY operation",
                (run_id,),
            )
        ]
    assert active == 0 and phase == "completed"
    with socket.socket() as probe:
        probe.settimeout(1)
        listening = probe.connect_ex(("127.0.0.1", 8779)) == 0
    assert not listening
    return {
        "experiment": "EXP-139",
        "result": "passed_bounded_local_scope",
        "execution_source": activation["source_sha"],
        "manifest_sha256": activation["manifest_sha256"],
        "ledger": ledger,
        "run_id": run_id,
        "thread_id": record["thread_id"],
        "status": record["status"],
        "evidence_complete": True,
        "completion_basis": record["completion_basis"],
        "closure": {
            key: record.get("evidence_closure", {}).get(key)
            for key in ("version", "reason", "item_count", "turn_count")
        },
        "precheck": {
            key: record.get("precheck", {}).get(key)
            for key in ("installed", "call_count")
        },
        "precheck_recomputed_from_bound_calls": checks,
        "commands": commands,
        "graph_result": graph["graph_result"],
        "fresh_write_attempts": writes,
        "cumulative_write_attempts": {"git_push": 2, "pr_create": 1},
        "effects": effects,
        "publication_phase": phase,
        "active_grants": active,
        "runner_listening": listening,
        "cleanup_verified": True,
        "controller_cleanup": "confirmed",
        "readback": readback,
        "scope": "single_user_local_fixed_report_only",
        "limitations": [
            "same_uid_relay_process_attachment_unverified",
            "historical_rotated_token_scan_unverified",
            "not_arbitrary_issue_implementation",
            "not_hosted_or_multi_user_acceptance",
        ],
        "historical_results_preserved": [
            "OBSERVATION.json",
            "RECOVERY-OBSERVATION.json",
            "AMEND05-OBSERVATION.json",
            "AMEND06-OBSERVATION.json",
            "AMEND07-OBSERVATION.json",
        ],
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    value = observe(parser.parse_args().state.resolve())
    Path(__file__).with_name("AMEND08-OBSERVATION.json").write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                key: value[key]
                for key in (
                    "result",
                    "ledger",
                    "cumulative_write_attempts",
                    "active_grants",
                )
            }
        )
    )
