"""Credential-free product handoff tests with fake provider transport."""

from contextlib import closing
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest

from laomedo.github_mediation import KnownRejected, MediationError, MediationStore
from laomedo.output_contract import requirements
from laomedo.publication_controller import PublicationController
from laomedo.verified_stage import VerifiedStage


class PublicationHandoffTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "mediator.sqlite"
        self.clock = [1000.0]
        self.monotonic = [100.0]
        self.store = MediationStore(self.path, now=lambda: self.clock[0],
                                   monotonic=lambda: self.monotonic[0],
                                   workflow_change_classifier=lambda *_: False)
        self.repository = "example/disposable"
        self.grant, self.token = self.issue("run-a")
        self.reference = requirements({"schema_version": 1, "fields": [
            {"name": "task_outcome", "type": "string", "required": True,
             "checks": {"enum": ["success", "failure"]}},
            {"name": "report", "type": "string", "required": True,
             "checks": {"nonempty": True}}]})
        self.envelope = {"schema_version": "laomedo.agent-submission.v1",
                         "submission": {"task_outcome": "success", "report": "done"},
                         "task_outcome": "success", "executor_status": "completed",
                         "evidence_complete": True,
                         "requirements_revision": self.reference["requirements_revision"]}
        self.artifact = VerifiedStage("run-a", "attempt-a", self.repository,
                                     "run-a-branch", "a" * 40, "b" * 40,
                                     sha256(b"fake-bundle").hexdigest(), "c" * 64,
                                     b"fake-bundle")
        self.calls = []

    def issue(self, run):
        return self.store.issue(run_id=run, invocation_id=run + "-invocation",
                                repository=self.repository, branch=run + "-branch",
                                operations={"git_push", "pr_create", "pr_list"},
                                ttl_seconds=50, lease_token=run + "-lease",
                                lease_scope="scope", service_instance="service")

    def begin(self):
        return self.store.begin_publication_handoff(
            token=self.token, repository=self.repository, requirements=self.reference,
            deadline=1030, deadline_monotonic=130)

    def pushed(self):
        # A fake provider receipt for a verified-stage digest. The real bundle
        # verifier has its own pinned-runtime tests; this does not bypass it
        # in a deployed resolver or claim real GitHub acceptance.
        with closing(self.store._connect()) as db, db:
            db.execute("INSERT INTO effects (run_id,effect_id,request_hash,repository,operation,"
                       "target_key,state,grant_id,stage_digest) VALUES "
                       "('run-a','push','hash',?,'git_push','target','confirmed',?,?)",
                       (self.repository, self.grant, self.artifact.stage_digest))

    def freeze(self, envelope=None):
        return self.store.freeze_publication_handoff(
            token=self.token, repository=self.repository,
            envelope=envelope or self.envelope, artifact=self.artifact,
            title="Reviewed output", body="Validated report")

    def transport(self, repo, operation, payload):
        self.assertEqual(repo, self.repository)
        self.assertEqual(operation, "pr_create")
        self.assertIs(payload["draft"], True)
        # Intent must exist DURABLY before the fake network write.
        with closing(self.store._connect()) as db:
            row = db.execute("SELECT state FROM effects WHERE effect_id=?",
                             ("handoff-pr:" + self.grant,)).fetchone()
        self.assertEqual(row["state"], "unknown")
        self.calls.append(deepcopy(payload))
        return {"number": 1}

    def readback(self, repo, number):
        request = self.calls[-1]
        return {"number": number, "draft": True, "title": request["title"],
                "body": request["body"], "base": request["base"],
                "head": {"repository": repo, "branch": request["head"], "sha": "b" * 40}}

    def publish(self, transport=None, readback=None):
        return self.store.publish_handoff(handoff_id=self.grant, token=self.token,
                                          repository=self.repository,
                                          transport=transport or self.transport,
                                          readback=readback or self.readback)

    def ready(self):
        self.begin()
        self.pushed()
        self.freeze()

    def refused(self, code, fn):
        with self.assertRaises(MediationError) as error:
            fn()
        self.assertEqual(error.exception.code, code)

    def test_success_is_draft_exact_effect_then_revoked(self):
        self.ready()
        self.assertEqual(self.publish()["phase"], "completed")
        self.assertEqual(len(self.calls), 1)
        self.refused("handoff_not_ready", self.publish)
        self.refused("grant_unavailable", lambda: self.store.invoke(
            token=self.token, repository=self.repository, operation="pr_list",
            payload={}, effect_id=None, transport=self.transport))

    def test_rejection_failure_interruption_unknown_evidence_never_publish(self):
        variants = [lambda e: e["submission"].update(report=""),
                    lambda e: (e["submission"].update(task_outcome="failure"), e.update(task_outcome="failure")),
                    lambda e: e.update(executor_status="interrupted", task_outcome="unknown"),
                    lambda e: e.update(evidence_complete="unknown"),
                    lambda e: e.update(evidence_complete=False),
                    lambda e: e.update(requirements_revision="sha256:" + "0" * 64)]
        for mutate in variants:
            with self.subTest(mutate=mutate):
                # Each variant uses an independent DB, run and original grant.
                self.setUp()
                self.begin(); self.pushed()
                envelope = deepcopy(self.envelope); mutate(envelope)
                self.freeze(envelope)
                self.assertEqual(self.publish()["phase"], "rejected")
                self.assertEqual(self.calls, [])

    def test_phase_ends_all_old_agent_operations_including_bundle_capture(self):
        self.ready()
        for op in ("pr_create", "pr_list", "bundle_freeze", "bundle_status", "git_push"):
            # Capture validates its request structure first, then phase.
            self.store.stage_freezer = lambda *_: {"status": "frozen"}
            self.store.verified_stage_resolver = lambda *_: self.artifact
            payload = ({"attempt_id": "a"} if op == "bundle_freeze" else
                       {"stage_attempt_id": "a", "commit": "b" * 40} if op == "bundle_status" else
                       {"branch": "run-a-branch", "commit": "b" * 40} if op == "git_push" else {})
            self.refused("agent_handoff_ended", lambda: self.store.invoke(
                token=self.token, repository=self.repository, operation=op, payload=payload,
                effect_id="attack" if op in {"pr_create", "git_push"} else None,
                transport=self.transport))

    def test_no_graph_operation_can_register_or_publish_handoff(self):
        for op in ("begin_publication_handoff", "publish_handoff"):
            self.refused("unsupported_operation", lambda: self.store.invoke(
                token=self.token, repository=self.repository, operation=op,
                payload={"accepted": True, "_handoff_id": self.grant}, effect_id="forged",
                transport=self.transport))
        self.assertEqual(self.calls, [])

    def test_missing_push_or_foreign_artifact_refuses(self):
        self.begin()
        self.refused("publication_push_unconfirmed", self.freeze)
        self.pushed()
        old = self.artifact
        from dataclasses import replace
        self.artifact = replace(old, run_id="other")
        self.refused("publication_artifact_mismatch", self.freeze)
        self.artifact = replace(old, bundle=b"tampered")
        self.refused("publication_artifact_unverified", self.freeze)

    def test_expiry_and_renewals_cannot_reset_dispatch_deadline(self):
        self.ready()
        self.clock[0] = 1029; self.monotonic[0] = 129
        self.assertTrue(self.store.renew_grant(self.grant, 60))
        self.assertTrue(self.store.renew_lease(run_id="run-a", lease_token="run-a-lease",
                         lease_scope="scope", ttl_seconds=60))
        self.clock[0] = 1031; self.monotonic[0] = 131
        self.assertEqual(self.publish()["phase"], "expired")
        self.assertEqual(self.calls, [])

    def test_monotonic_expiry_survives_wall_clock_rollback(self):
        self.ready(); self.clock[0] = 999; self.monotonic[0] = 131
        self.assertEqual(self.publish()["phase"], "expired")

    def test_revoked_grant_is_not_resurrected(self):
        self.ready(); self.store.revoke_run("run-a")
        self.assertFalse(self.store.renew_grant(self.grant, 50))
        self.assertEqual(self.publish()["phase"], "expired")
        self.assertEqual(self.calls, [])

    def test_cancel_during_provider_call_preserves_receipt_without_false_completion(self):
        self.ready()
        def cancelled(repo, op, payload):
            result = self.transport(repo, op, payload)
            self.store.end_publication_handoff(self.grant, "cancelled")
            return result
        result = self.publish(transport=cancelled)
        self.assertEqual(result["phase"], "cancelled")
        self.assertEqual(result["publication"]["state"], "unknown")
        self.assertEqual(self.store.effect("run-a", "handoff-pr:" + self.grant)["state"], "confirmed")
        self.assertEqual(len(self.calls), 1)

    def test_deadline_during_readback_does_not_report_success(self):
        self.ready()
        def late(repo, number):
            observed = self.readback(repo, number)
            self.monotonic[0] = 131
            return observed
        self.assertEqual(self.publish(readback=late)["phase"], "expired")
        self.assertEqual(len(self.calls), 1)

    def test_connection_removed_during_readback_cannot_complete_handoff(self):
        current = [True]
        self.store.connection_is_current = lambda *_: current[0]
        self.grant, self.token = self.store.issue(
            run_id="run-a", invocation_id="connected", repository=self.repository,
            operations={"git_push", "pr_create"}, branch="run-a-branch", ttl_seconds=50,
            connection_id="connection", connection_generation=1)
        self.ready()
        def removed(repo, number):
            observed = self.readback(repo, number)
            current[0] = False
            return observed
        result = self.publish(transport=lambda repo, op, payload, **_: self.transport(repo, op, payload),
                              readback=removed)
        self.assertEqual(result["phase"], "expired")
        self.assertEqual(result["publication"]["state"], "unknown")

    def test_unknown_write_never_resends(self):
        self.ready()
        def lost(repo, op, payload):
            self.transport(repo, op, payload)
            raise TimeoutError("private provider error")
        self.assertEqual(self.publish(transport=lost)["phase"], "unknown")
        self.refused("handoff_not_ready", self.publish)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.store.effect("run-a", "handoff-pr:" + self.grant)["state"], "unknown")

    def test_complete_rejection_is_failed(self):
        self.ready()
        def rejected(*_):
            raise KnownRejected("provider_rejected")
        self.assertEqual(self.publish(transport=rejected)["phase"], "failed")

    def test_readback_checks_actual_draft_head_commit_and_marker(self):
        for key in ("draft", "sha", "body", "base", "title"):
            with self.subTest(key=key):
                self.setUp(); self.ready()
                def bad(repo, number):
                    data = self.readback(repo, number)
                    if key == "sha": data["head"]["sha"] = "0" * 40
                    else: data[key] = False if key == "draft" else "wrong"
                    return data
                self.assertEqual(self.publish(readback=bad)["phase"], "unknown")
                self.assertEqual(len(self.calls), 1)

    def test_inflight_agent_effect_prevents_handoff(self):
        self.begin(); self.pushed()
        entered = threading.Event(); release = threading.Event()
        def blocked(*_):
            entered.set(); release.wait(2)
            return {"number": 7}
        worker = threading.Thread(target=lambda: self.store.invoke(
            token=self.token, repository=self.repository, operation="pr_create",
            payload={"head": "run-a-branch", "base": "main", "marker": "m"},
            effect_id="agent-inflight", transport=blocked))
        worker.start(); self.assertTrue(entered.wait(1))
        self.assertEqual(self.freeze()["phase"], "unknown")
        release.set(); worker.join(2)
        self.refused("handoff_not_ready", self.publish)

    def test_runner_loss_revokes_same_grant_other_run_survives(self):
        self.ready(); _, other = self.issue("run-b")
        self.store.revoke_lease(run_id="run-a", lease_token="run-a-lease", lease_scope="scope")
        self.assertEqual(self.publish()["phase"], "expired")
        result = self.store.invoke(token=other, repository=self.repository, operation="pr_list",
                                   payload={}, effect_id=None, transport=lambda *_: {"items": []})
        self.assertEqual(result["state"], "confirmed")

    def test_startup_sweep_revokes_without_replaying(self):
        self.ready()
        controller = PublicationController(self.store, lifetime_seconds=30,
            artifact_resolver=None, transport=self.transport, readback=self.readback, describe=None)
        self.assertEqual(controller.recover(), 1)
        self.assertEqual(controller.recover(), 0)
        self.refused("handoff_not_ready", self.publish)
        self.assertEqual(self.calls, [])

    def test_controller_owns_lease_until_terminal(self):
        self.pushed()
        lease = SimpleNamespace(grant_id=self.grant, grant_secret=lambda: self.token,
                                lost=threading.Event(), stop_event=threading.Event(),
                                finish=lambda: self.calls.append("lease-finished"))
        controller = PublicationController(self.store, lifetime_seconds=30,
            artifact_resolver=lambda *_: self.artifact, transport=self.transport,
            readback=self.readback, describe=lambda _: ("Title", "Body"))
        record = {"run_id": "run-a", "github_scope": {"repository": self.repository},
                  "output_requirements": self.reference,
                  "requirements_revision": self.reference["requirements_revision"],
                  "status": "completed", "snapshot_ready": True,
                  "controller_cleanup": "confirmed", "container_ownership": {"cleanup_verified": True},
                  "answer": '{"task_outcome":"success","report":"done"}', "evidence_complete": True}
        controller.register(lease, record)
        self.assertTrue(controller.finish_agent(record))
        self.assertEqual(self.calls, [])
        self.assertEqual(controller.publish("run-a")["phase"], "completed")
        self.assertEqual(self.calls[-1], "lease-finished")
        self.refused("handoff_not_owned", lambda: controller.publish("run-a"))

    def test_no_default_or_infinite_handoff_deadline(self):
        for lifetime in (None, False, 0, float("inf"), float("nan"), threading.TIMEOUT_MAX + 1):
            with self.assertRaises(ValueError):
                PublicationController(self.store, lifetime_seconds=lifetime,
                    artifact_resolver=None, transport=None, readback=None, describe=None)

    def test_controller_ends_known_non_success_without_waiting_for_publisher(self):
        for answer, complete in (("failure", True), ("success", "unknown")):
            with self.subTest(answer=answer, complete=complete):
                self.setUp()
                finished = []
                lease = SimpleNamespace(grant_id=self.grant, grant_secret=lambda: self.token,
                    lost=threading.Event(), stop_event=threading.Event(), finish=lambda: finished.append(True))
                def forbidden(*_):
                    self.fail("invalid result must not resolve artifact or contact provider")
                controller = PublicationController(self.store, lifetime_seconds=30,
                    artifact_resolver=forbidden, transport=forbidden, readback=forbidden, describe=forbidden)
                record = {"run_id": "run-a", "github_scope": {"repository": self.repository},
                    "output_requirements": self.reference, "requirements_revision": self.reference["requirements_revision"],
                    "status": "completed", "snapshot_ready": True, "controller_cleanup": "confirmed",
                    "container_ownership": {"cleanup_verified": True}, "evidence_complete": complete,
                    "answer": '{"task_outcome":"' + answer + '","report":"done"}'}
                controller.register(lease, record)
                self.assertFalse(controller.finish_agent(record))
                self.assertEqual(self.store.publication_handoff(self.grant)["phase"], "rejected")
                self.assertEqual(finished, [True])
                self.assertNotIn("run-a", controller.owned)

    def test_runner_publication_api_requires_auth_and_empty_graph_body(self):
        from laomedo.local_runner import LocalRunner, serve
        from urllib import request, error
        import json
        self.ready()
        finished = []
        lease = SimpleNamespace(finish=lambda: finished.append(True), stop_event=threading.Event())
        controller = PublicationController(self.store, lifetime_seconds=30,
            artifact_resolver=None, transport=self.transport, readback=self.readback, describe=None)
        controller.owned["run-a"] = (lease, self.token, self.repository, self.grant)
        runner = LocalRunner.__new__(LocalRunner)
        runner.api_token = "dummy-runner-token"
        runner.publication_controller = controller
        server = serve(runner, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        endpoint = "http://127.0.0.1:" + str(server.server_port) + "/v1/runs/run-a/publish"
        try:
            def post(payload, token="dummy-runner-token"):
                req = request.Request(endpoint, data=json.dumps(payload).encode(), method="POST",
                                      headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
                return request.urlopen(req, timeout=3)
            with self.assertRaises(error.HTTPError) as refusal:
                post({}, "wrong-token")
            self.assertEqual(refusal.exception.code, 401)
            with self.assertRaises(error.HTTPError) as refusal:
                post({"accepted": True, "grant": self.token})
            self.assertEqual(refusal.exception.code, 400)
            self.assertEqual(self.calls, [])
            with post({}) as response:
                result = json.load(response)
            self.assertEqual(result["publication_handoff"]["phase"], "completed")
            self.assertEqual(len(self.calls), 1)
            self.assertEqual(finished, [True])
        finally:
            server.shutdown(); server.server_close(); thread.join(3)


if __name__ == "__main__":
    unittest.main()
