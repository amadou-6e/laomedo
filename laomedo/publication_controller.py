"""Trusted runner-side owner of finite leases through downstream validation.

Opt-in host composition only. It supplies no credential, ambient gh fallback,
or grant-issuing endpoint. The normal runner's behavior remains unchanged.
"""

from copy import deepcopy
import json
import math
import threading

from .github_mediation import MediationError


class PublicationController:
    def __init__(self, store, *, lifetime_seconds, artifact_resolver, transport,
                 readback, describe):
        if (type(lifetime_seconds) not in {int, float} or
                not math.isfinite(lifetime_seconds) or lifetime_seconds <= 0):
            raise ValueError("handoff_deadline_required")
        self.store = store
        self.lifetime = lifetime_seconds
        self.artifact_resolver = artifact_resolver
        self.transport = transport
        self.readback = readback
        self.describe = describe
        self.owned = {}
        self.lock = threading.RLock()

    def register(self, lease, record):
        """Host calls before dispatch; no graph may submit a grant or deadline."""
        requirements = record.get("output_requirements")
        repository = record["github_scope"]["repository"]
        token = lease.grant_secret()
        with self.lock:
            if record["run_id"] in self.owned:
                raise MediationError("handoff_already_registered")
            handoff_id = self.store.begin_publication_handoff(
                token=token, repository=repository, requirements=requirements,
                deadline=self.store.now() + self.lifetime,
                deadline_monotonic=self.store.monotonic() + self.lifetime)
            if handoff_id != lease.grant_id:
                self.store.end_publication_handoff(handoff_id, "failed")
                raise MediationError("handoff_lease_mismatch")
            self.owned[record["run_id"]] = (lease, token, repository, handoff_id)
        # This waits only on the original deadline. It never extends the lease
        # when the graph takes longer or when the agent finishes.
        timer = threading.Timer(self.lifetime, self.cancel,
                                args=(record["run_id"], "expired"))
        timer.daemon = True
        timer.start()

    def finish_agent(self, record):
        """Called after executor cleanup, before downstream graph publication."""
        with self.lock:
            owned = self.owned.get(record["run_id"])
            if owned is None:
                return False
            lease, token, repository, handoff_id = owned
            if (record.get("status") != "completed" or
                    record.get("snapshot_ready") is not True or
                    record.get("controller_cleanup") != "confirmed" or
                    record.get("container_ownership", {}).get("cleanup_verified") is not True or
                    lease.lost.is_set()):
                self.cancel(record["run_id"], "failed")
                return False
            try:
                submission = json.loads(record["answer"])
                envelope = {"schema_version": "laomedo.agent-submission.v1",
                            "submission": submission, "answer": record["answer"],
                            "task_outcome": submission.get("task_outcome", "unknown"),
                            "executor_status": record["status"],
                            # Unknown stays unknown until the real runner has
                            # an independently verified completeness closure.
                            "evidence_complete": record.get("evidence_complete", "unknown"),
                            "requirements_revision": record.get("requirements_revision")}
                artifact = self.artifact_resolver(deepcopy(record), handoff_id)
                title, body = self.describe(deepcopy(record))
                frozen = self.store.freeze_publication_handoff(
                    token=token, repository=repository, envelope=envelope,
                    artifact=artifact, title=title, body=body)
                if frozen["phase"] != "validation_pending":
                    self.cancel(record["run_id"], "unknown")
                    return False
            except Exception:
                self.cancel(record["run_id"], "failed")
                return False
            return True

    def publish(self, run_id):
        """A graph can request this; validation comes from frozen host records."""
        with self.lock:
            owned = self.owned.get(run_id)
            if owned is None:
                raise MediationError("handoff_not_owned")
            lease, token, repository, handoff_id = owned
        try:
            result = self.store.publish_handoff(
                handoff_id=handoff_id, token=token, repository=repository,
                transport=self.transport, readback=self.readback)
        except Exception:
            self.cancel(run_id, "unknown")
            raise
        finally:
            self.cancel(run_id, "unknown")
        return result

    def cancel(self, run_id, phase="cancelled"):
        with self.lock:
            owned = self.owned.pop(run_id, None)
        if owned is None:
            return
        lease, _, _, handoff_id = owned
        self.store.end_publication_handoff(handoff_id, phase)
        # Revoke synchronously before any potentially slow cleanup. The lease
        # supervisor still owns exact container cleanup and its startup sweep.
        try:
            lease.finish()
        except Exception:
            lease.stop_event.set()

    def recover(self):
        """Explicit single-controller startup sweep, never replay a write.

        Call only after the old controller is known dead. Independent lease
        revocation also covers crashes without a new controller starting.
        """
        from contextlib import closing
        with closing(self.store._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT grant_id FROM publication_handoffs WHERE phase "
                              "IN ('agent_active','validation_pending','publication_pending')").fetchall()
            for row in rows:
                self.store._end_handoff(db, row["grant_id"], "unknown")
        return len(rows)
