"""Credential-free negative control for the current same-user grant issuer.

This demonstrates a missing boundary. It must never be read as approval.
"""

from datetime import datetime, timedelta, timezone
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory

from laomedo.work_graph.github import import_pages
from laomedo.work_graph.grants import LocalGrantAuthority, _host_principal


CORPUS = Path(__file__).resolve().parents[1] / "exp16" / "corpus.json"


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--child":
        corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
        snapshot = import_pages("verify/exp16", corpus["base"],
                                fetched_at="2026-10-05T10:00:00+00:00")
        authority = LocalGrantAuthority(Path(sys.argv[2]))
        authority.issue(work_key="github:S-20", graph_snapshot=snapshot,
                        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
                        timeout_seconds=60, max_turns=0)
        return 0

    with TemporaryDirectory(prefix="laomedo-exp95-") as private:
        ledger = Path(private) / "grants.sqlite3"
        LocalGrantAuthority(ledger)
        parent_principal = _host_principal()
        child = subprocess.run([sys.executable, "-m", "experiments.exp95.probe",
                                "--child", str(ledger)], capture_output=True,
                               text=True, timeout=30, check=False)
        with closing(sqlite3.connect(ledger)) as db:
            issued = db.execute("SELECT COUNT(*) FROM grants").fetchone()[0]
            recorded = db.execute("SELECT operator_id FROM grants").fetchone()
        result = {
            "same_principal": recorded is not None and recorded[0] == parent_principal,
            "child_exit_zero": child.returncode == 0,
            "grants_issued_without_human_approval": issued,
            "boundary_passed": False,
        }
        print(json.dumps(result, sort_keys=True))
        return 0 if result["same_principal"] and result["child_exit_zero"] and issued == 1 else 1


if __name__ == "__main__":
    raise SystemExit(main())
