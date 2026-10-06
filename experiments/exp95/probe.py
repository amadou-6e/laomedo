"""Credential-free same-user controls for the #95 approval boundary.

Phase 1 (unchanged negative control): a separate same-user process can mint a
grant from the legacy ``LocalGrantAuthority.issue()`` fixture.

Phase 2: a separate same-user *attacker* process, holding no authenticator key,
tries to obtain a redeemable grant from ``ProtectedApprovalAuthority`` by
(a) writing a forged grant row into the ledger, (b) editing an approved request,
and (c) replaying a real approval's assertion onto its own request. Each must be
refused at approval or redemption. The probe also records the residual limits
that need the OS boundary (a separate service identity and ACLs).
"""

from contextlib import closing
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory

from laomedo.work_graph.approval import (ProtectedApprovalAuthority, TrustAnchor,
                                         derive_challenge)
from laomedo.work_graph.github import import_pages
from laomedo.work_graph.grants import LocalGrantAuthority, _host_principal
from laomedo.work_graph.webauthn import b64url_decode
from laomedo.workflow_run_store import LaunchError


CORPUS = Path(__file__).resolve().parents[1] / "exp16" / "corpus.json"
TESTS = Path(__file__).resolve().parents[2] / "tests"


def _request(work_key="github:S-20"):
    return {"work_key": work_key, "work_url": "https://github.com/verify/exp16/issues/20",
            "body_digest": "sha256:" + "1" * 64, "content_digest": "sha256:" + "2" * 64,
            "task_digest": "sha256:" + sha256(b"Synthetic task").hexdigest(),
            "graph_snapshot_id": "sha256:" + "3" * 64, "runner": "langflow-local",
            "scope": "stage-launch",
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
            "timeout_seconds": 60, "max_turns": 0}


def _binding(request):
    return {"work_snapshot": {"key": request["work_key"]},
            "selected_content_digest": request["content_digest"]}


def legacy_child(ledger):
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    snapshot = import_pages("verify/exp16", corpus["base"],
                            fetched_at="2026-10-05T10:00:00+00:00")
    LocalGrantAuthority(Path(ledger)).issue(
        work_key="github:S-20", graph_snapshot=snapshot,
        expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        timeout_seconds=60, max_turns=0)


def attacker_child(ledger, anchor_path, approved_grant):
    """Same-user process with ledger write access but no authenticator key."""
    authority = ProtectedApprovalAuthority(Path(ledger), TrustAnchor.load(Path(anchor_path)))
    outcomes = {}

    def refused(label, action):
        try:
            action()
            outcomes[label] = "ACCEPTED"
        except LaunchError as exc:
            outcomes[label] = "refused:" + str(exc)

    own = authority.submit(_request("github:ATTACKER"))
    with closing(sqlite3.connect(ledger)) as db, db:
        approved = db.execute("SELECT * FROM grants WHERE grant_id=?",
                              (approved_grant,)).fetchone()
        # (a) forge: mark own request approved and copy a real signature onto it
        db.execute("UPDATE requests SET state='approved' WHERE request_id=?", (own["request_id"],))
        db.execute("INSERT INTO grants VALUES ('grant-forged', ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                   (own["request_id"],) + tuple(approved[2:9]))
    refused("forged_ledger_row", lambda: authority("grant-forged", _binding(own["request"])))
    # (b) edit the approved request's work key and recompute its digest column
    with closing(sqlite3.connect(ledger)) as db, db:
        request_id = db.execute("SELECT request_id FROM grants WHERE grant_id=?",
                                (approved_grant,)).fetchone()[0]
        original = json.loads(db.execute("SELECT request_json FROM requests WHERE request_id=?",
                                         (request_id,)).fetchone()[0])
        edited = dict(original, work_key="github:ATTACKER")
        from laomedo.work_graph.approval import request_digest
        db.execute("UPDATE requests SET request_json=?, request_digest=? WHERE request_id=?",
                   (json.dumps(edited, sort_keys=True, separators=(",", ":")),
                    request_digest(edited), request_id))
    refused("edited_approved_request", lambda: authority(approved_grant, _binding(edited)))
    # (c) replay the real assertion onto a fresh request of the attacker's own
    fresh = authority.submit(_request("github:ATTACKER-2"))
    # Row layout: grant_id, request_id, credential_id, authenticator_data,
    # client_data_json, signature, sign_count, anchor_fingerprint, approved_at, redeemed_at
    assertion = {"credential_id": approved[2], "authenticator_data": approved[3],
                 "client_data_json": approved[4], "signature": approved[5]}
    refused("replayed_assertion", lambda: authority.approve(fresh["request_id"], assertion))
    print(json.dumps(outcomes, sort_keys=True))


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--legacy-child":
        legacy_child(sys.argv[2])
        return 0
    if len(sys.argv) == 5 and sys.argv[1] == "--attacker-child":
        attacker_child(*sys.argv[2:])
        return 0

    with TemporaryDirectory(prefix="laomedo-exp95-") as private:
        root = Path(private)
        legacy = root / "grants.sqlite3"
        LocalGrantAuthority(legacy)
        child = subprocess.run([sys.executable, "-m", "experiments.exp95.probe",
                                "--legacy-child", str(legacy)], capture_output=True,
                               text=True, timeout=60, check=False)
        with closing(sqlite3.connect(legacy)) as db:
            issued = db.execute("SELECT COUNT(*) FROM grants").fetchone()[0]
            recorded = db.execute("SELECT operator_id FROM grants").fetchone()

        # Protected authority with a software fixture authenticator (tests only).
        sys.path.insert(0, str(TESTS))
        from test_approval_authority import FixtureAuthenticator
        key = FixtureAuthenticator()
        anchor = root / "anchor.json"
        anchor.write_text(json.dumps({"alg": "ES256", "credential_id": key.credential_id,
            "x": f"{key.public[0]:064x}", "y": f"{key.public[1]:064x}",
            "rp_id": "laomedo.local", "origin": "https://laomedo.local"}), encoding="utf-8")
        ledger = root / "approval.sqlite3"
        authority = ProtectedApprovalAuthority(ledger, TrustAnchor.load(anchor))
        submitted = authority.submit(_request())
        with closing(sqlite3.connect(ledger)) as db:
            nonce = b64url_decode(db.execute("SELECT nonce FROM requests").fetchone()[0])
        grant_id = authority.approve(submitted["request_id"], key.assert_(derive_challenge(
            submitted["request_id"], nonce, submitted["request_digest"])))
        attack = subprocess.run([sys.executable, "-m", "experiments.exp95.probe",
                                 "--attacker-child", str(ledger), str(anchor), grant_id],
                                capture_output=True, text=True, timeout=120, check=False)
        outcomes = json.loads(attack.stdout.strip().splitlines()[-1]) if attack.returncode == 0 else {}
        refused_all = bool(outcomes) and all(v.startswith("refused:") for v in outcomes.values())
        result = {
            "legacy_same_principal": recorded is not None and recorded[0] == _host_principal(),
            "legacy_grants_issued_without_human_approval": issued,
            "legacy_child_exit_zero": child.returncode == 0,
            "protected_attacker_outcomes": outcomes,
            "protected_minting_refused": refused_all,
            # Residual limits that only the OS boundary closes; reported, not hidden.
            "trust_anchor_writable_by_same_user": os.access(anchor, os.W_OK),
            "os_service_identity_and_acl_implemented": False,
            "human_ceremony_exercised": False,
            "boundary_passed": False,
        }
        print(json.dumps(result, sort_keys=True))
        ok = (result["legacy_same_principal"] and issued == 1 and result["legacy_child_exit_zero"]
              and refused_all)
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
