"""Host-only publication handoff over an existing revocable mediator grant.

None of these methods is an agent HTTP operation. A graph's validation result
is a request to the controller, never authority or proof of a valid artifact.
"""

from contextlib import closing
from hashlib import sha256
import json
import math
import re

from .output_contract import evaluate_envelope, verify_requirements


TERMINAL = frozenset({"completed", "rejected", "failed", "unknown", "expired", "cancelled"})


def _deny(code):
    from .github_mediation import MediationError
    raise MediationError(code)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


class HandoffStore:
    """Internal methods inherited by the durable mediator, not its public API."""

    def _handoff_gate(self, db, grant, operation, handoff_id, payload):
        row = db.execute("SELECT * FROM publication_handoffs WHERE grant_id=?",
                         (grant["grant_id"],)).fetchone()
        if row is None:
            if handoff_id is not None:
                _deny("handoff_unavailable")
            return
        if self.now() >= row["deadline"] or self.monotonic() >= row["deadline_monotonic"]:
            _deny("handoff_expired")
        if row["phase"] in TERMINAL:
            _deny("handoff_terminal")
        if handoff_id is None:
            if row["phase"] != "agent_active":
                # Freeze/status also touch the private bundle state. Deny all
                # old agent bearer operations after execution, including reads.
                _deny("agent_handoff_ended")
        elif (handoff_id != grant["grant_id"] or row["phase"] != "publication_pending"
              or operation != "pr_create" or _json(payload) != row["request_json"]):
            _deny("publisher_binding_mismatch")

    def begin_publication_handoff(self, *, token, repository, requirements,
                                  deadline, deadline_monotonic):
        """Called by the host before dispatch, while the original lease is live."""
        reference = verify_requirements(requirements)
        if any(type(v) not in {int, float} or not math.isfinite(v)
               for v in (deadline, deadline_monotonic)):
            _deny("handoff_deadline_required")
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            grant = self._grant(db, token, repository, "pr_create")
            if deadline <= self.now() or deadline_monotonic <= self.monotonic():
                _deny("handoff_expired")
            if db.execute("SELECT 1 FROM publication_handoffs WHERE grant_id=?",
                          (grant["grant_id"],)).fetchone():
                _deny("handoff_already_registered")
            db.execute("INSERT INTO publication_handoffs "
                       "(grant_id,run_id,phase,deadline,deadline_monotonic,requirements_json) "
                       "VALUES (?,?,'agent_active',?,?,?)",
                       (grant["grant_id"], grant["run_id"], deadline,
                        deadline_monotonic, _json(reference)))
            db.execute("UPDATE grants SET expires_at=MIN(expires_at,?), "
                       "expires_monotonic=MIN(expires_monotonic,?) WHERE grant_id=?",
                       (deadline, deadline_monotonic, grant["grant_id"]))
            return grant["grant_id"]

    def freeze_publication_handoff(self, *, token, repository, envelope,
                                   artifact, title, body):
        """Freeze host-observed output and an already verified, pushed bundle.

        The host supplies VerifiedStage from its private resolver, never from
        graph data. Its exact digest must already have a confirmed push receipt
        under this grant. Arbitrary caller paths or claimed graph hashes fail.
        """
        from .verified_stage import VerifiedStage
        if (not isinstance(artifact, VerifiedStage) or
                sha256(artifact.bundle).hexdigest() != artifact.bundle_sha256 or
                not re.fullmatch(r"[0-9a-f]{40}", artifact.commit) or
                not all(isinstance(x, str) and x for x in (title, body))):
            _deny("publication_artifact_unverified")
        frozen_envelope = _json(envelope)
        if len(frozen_envelope.encode()) > 512 * 1024:
            _deny("publication_output_too_large")
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            grant = self._grant(db, token, repository, "pr_create")
            row = db.execute("SELECT * FROM publication_handoffs WHERE grant_id=?",
                             (grant["grant_id"],)).fetchone()
            if row is None or row["phase"] != "agent_active":
                _deny("handoff_unavailable")
            if (artifact.run_id != grant["run_id"] or artifact.repository != repository or
                    artifact.branch != grant["branch"]):
                _deny("publication_artifact_mismatch")
            if db.execute("SELECT 1 FROM effects WHERE run_id=? AND grant_id=? "
                          "AND operation='git_push' AND state='confirmed' AND stage_digest=?",
                          (grant["run_id"], grant["grant_id"], artifact.stage_digest)).fetchone() is None:
                _deny("publication_push_unconfirmed")
            # Serialize phase transition against new effect reservations.
            # An in-flight write already has an unknown intent. Refuse the
            # handoff rather than let a late agent effect race publication.
            if db.execute("SELECT 1 FROM effects WHERE grant_id=? AND state='unknown'",
                          (grant["grant_id"],)).fetchone():
                self._end_handoff(db, grant["grant_id"], "unknown")
                return {"phase": "unknown"}
            marker = "<!-- laomedo-handoff:" + grant["grant_id"] + " -->"
            request = {"head": grant["branch"], "base": grant["base_branch"],
                       "title": title, "body": body + "\n\n" + marker,
                       "marker": marker, "draft": True}
            db.execute("UPDATE publication_handoffs SET phase='validation_pending', "
                       "artifact_digest=?,artifact_commit=?,request_json=?,effect_id=?,envelope_json=? WHERE grant_id=?",
                       (artifact.stage_digest, artifact.commit, _json(request), "handoff-pr:" + grant["grant_id"],
                        frozen_envelope, grant["grant_id"]))
            return {"phase": "validation_pending", "handoff_id": grant["grant_id"]}

    def _end_handoff(self, db, handoff_id, phase):
        db.execute("UPDATE publication_handoffs SET phase=? WHERE grant_id=? AND phase "
                   "NOT IN ('completed','rejected','failed','unknown','expired','cancelled')",
                   (phase, handoff_id))
        db.execute("UPDATE grants SET revoked_at=? WHERE grant_id=? AND revoked_at IS NULL",
                   (self.now(), handoff_id))

    def end_publication_handoff(self, handoff_id, phase="cancelled"):
        if phase not in TERMINAL:
            _deny("handoff_terminal_required")
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._end_handoff(db, handoff_id, phase)

    def publication_handoff(self, handoff_id):
        with closing(self._connect()) as db:
            row = db.execute("SELECT run_id,phase,deadline,artifact_digest FROM "
                             "publication_handoffs WHERE grant_id=?", (handoff_id,)).fetchone()
        return dict(row) if row else None

    def publish_handoff(self, *, handoff_id, token, repository, transport, readback):
        """Controller recomputes validation; exact request uses Q16 journal once.

        `readback` is an injected host provider read, not a caller's claimed
        receipt. Unknown outcomes revoke the capability and are not resent.
        """
        from .github_mediation import MediationError
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM publication_handoffs WHERE grant_id=?",
                             (handoff_id,)).fetchone()
            if row is None or row["phase"] != "validation_pending":
                _deny("handoff_not_ready")
            # The old agent lane is closed. Check the same grant's remaining
            # lifetime and connection without pretending to be an agent call.
            grant = db.execute("SELECT * FROM grants WHERE grant_id=?", (handoff_id,)).fetchone()
            valid_token = grant and sha256(token.encode()).hexdigest() == grant["token_hash"]
            if not valid_token or grant["repository"] != repository:
                _deny("publisher_binding_mismatch")
            if (grant["revoked_at"] is not None or grant["expires_at"] <= self.now() or
                    self.now() >= row["deadline"] or self.monotonic() >= row["deadline_monotonic"] or
                    not grant["issued_monotonic"] <= self.monotonic() < grant["expires_monotonic"]):
                self._end_handoff(db, handoff_id, "expired")
                return {"phase": "expired"}
            envelope = json.loads(row["envelope_json"])
            validation = evaluate_envelope(json.loads(row["requirements_json"]), envelope)
            if (validation["contract_status"] != "accepted" or
                    envelope.get("task_outcome") != "success" or
                    envelope.get("executor_status") != "completed" or
                    envelope.get("evidence_complete") is not True):
                self._end_handoff(db, handoff_id, "rejected")
                return {"phase": "rejected"}
            db.execute("UPDATE publication_handoffs SET phase='publication_pending' WHERE grant_id=?",
                       (handoff_id,))
            request = json.loads(row["request_json"])
        try:
            result = self.invoke(token=token, repository=repository, operation="pr_create",
                                 payload=request, effect_id=row["effect_id"], transport=transport,
                                 _handoff_id=handoff_id)
            if result["state"] == "confirmed":
                receipt = result["result"]
                observed = readback(repository, receipt["number"])
                if (type(receipt.get("number")) is not int or receipt["number"] < 1 or
                        observed.get("number") != receipt["number"] or
                        observed.get("draft") is not True or
                        observed.get("head", {}).get("repository") != repository or
                        observed.get("head", {}).get("branch") != request["head"] or
                        observed.get("head", {}).get("sha") != row["artifact_commit"] or
                        observed.get("base") != request["base"] or
                        observed.get("title") != request["title"] or
                        observed.get("body") != request["body"] or
                        request["marker"] not in observed.get("body", "")):
                    raise ValueError("publication_readback_mismatch")
                phase = "completed"
            else:
                phase = "failed" if result["state"] == "rejected" else "unknown"
        except MediationError:
            phase, result = "failed", {"state": "rejected", "error": "publication_refused"}
        except Exception:
            phase, result = "unknown", {"state": "unknown", "resent": False}
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT phase FROM publication_handoffs WHERE grant_id=?",
                                 (handoff_id,)).fetchone()
            live = db.execute("SELECT * FROM grants WHERE grant_id=?", (handoff_id,)).fetchone()
            if current["phase"] == "publication_pending" and (
                    live["revoked_at"] is not None or self.now() >= row["deadline"] or
                    self.monotonic() >= row["deadline_monotonic"] or
                    self.now() >= live["expires_at"] or
                    self.monotonic() >= live["expires_monotonic"] or
                    (live["connection_id"] is not None and not self._connection_current(
                        live["connection_id"], live["connection_generation"], repository))):
                self._end_handoff(db, handoff_id, "expired")
                return {"phase": "expired", "publication": {"state": "unknown"}}
            if current["phase"] != "publication_pending":
                # Cancellation can race a submitted remote effect. Retain the
                # Q16 receipt, but never turn a cancelled handoff into success.
                return {"phase": current["phase"], "publication": {"state": "unknown"}}
            self._end_handoff(db, handoff_id, phase)
        return {"phase": phase, "publication": result}
