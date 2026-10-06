"""The ordinary client cannot invoke the operator ceremony over HTTP."""

from http.client import HTTPConnection
from hashlib import sha256
import json
from pathlib import Path
from threading import Thread
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from laomedo.work_graph.approval_service import (ApprovalService,
                                                  LocalSavedFlowDispatch,
                                                  serve_loopback)
from laomedo.workflow_run_store import LaunchError


class FixtureAuthority:
    def __init__(self):
        self.anchor = type("Anchor", (), {"rp_id": "fixture.local",
                                           "origin": "https://fixture.local"})()
        self.request = None
        self.grant = None
        self.used = False
        self.denied = False

    def submit(self, request):
        self.request = dict(request)
        return {"request_id": "req-1", "request_digest": "sha256:reviewed",
                "challenge": "private-challenge", "request": self.request}

    def pending_request(self, request_id):
        if request_id != "req-1" or self.denied:
            raise LaunchError("approval_request_not_pending")
        return {"request_id": request_id, "request": self.request,
                "request_digest": "sha256:reviewed", "challenge": "private-challenge"}

    def deny(self, _request_id):
        self.denied = True

    def approve(self, request_id, assertion):
        if request_id != "req-1" or assertion != "signed-private-challenge":
            raise LaunchError("approval_assertion_invalid")
        self.grant = "grant-1"
        return self.grant

    def __call__(self, grant_id, binding):
        if grant_id != self.grant or self.used or binding != {"work": "reviewed"}:
            raise LaunchError("grant_invalid")
        self.used = True
        return {"grant_id": grant_id, "operator_authorized": True}


class ApprovalServiceTests(unittest.TestCase):
    def setUp(self):
        self.authority = FixtureAuthority()
        self.displayed = []
        self.ceremonies = []
        self.dispatches = []
        self.service = ApprovalService(
            self.authority,
            operator_display=lambda text, digest: self.displayed.append((text, digest)) or True,
            authenticator=lambda challenge, rp, origin: self.ceremonies.append(
                (challenge, rp, origin)) or "signed-" + challenge,
            dispatch=self.dispatch)
        self.server = serve_loopback(self.service)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.thread.join, 5)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def post(self, path, payload):
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            conn.request("POST", path, body=json.dumps(payload),
                         headers={"Content-Type": "application/json"})
            response = conn.getresponse()
            return response.status, response.read().decode("utf-8")
        finally:
            conn.close()

    def dispatch(self, grant_id, payload, authority):
        grant = authority(grant_id, {"work": "reviewed"})
        self.dispatches.append((grant, payload))
        return {"status": "dispatched"}

    def test_client_cannot_approve_or_launch_until_protected_review(self):
        status, submitted = self.post("/v1/requests", {"work_key": "reviewed"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(submitted), {"request_id": "req-1",
            "request_digest": "sha256:reviewed", "state": "pending"})
        self.assertNotIn("challenge", submitted)
        self.assertEqual(self.post("/v1/approve", {"request_id": "req-1"})[0], 404)
        launch = {"grant_id": "grant-1", "payload": {"task": "fixture"}}
        self.assertEqual(self.post("/v1/launch", launch)[0], 403)
        self.assertEqual(self.displayed, [])
        self.assertEqual(self.ceremonies, [])
        self.assertEqual(self.dispatches, [])

        self.assertEqual(self.service.review("req-1"), "grant-1")
        self.assertIn('"work_key": "reviewed"', self.displayed[0][0])
        self.assertEqual(self.displayed[0][1], "sha256:reviewed")
        self.assertEqual(self.ceremonies, [("private-challenge", "fixture.local",
                                           "https://fixture.local")])
        status, result = self.post("/v1/launch", launch)
        self.assertEqual((status, json.loads(result)), (200, {"status": "dispatched"}))
        self.assertEqual(self.post("/v1/launch", launch)[0], 403)
        self.assertEqual(len(self.dispatches), 1)

    def test_rejected_review_never_starts_authenticator(self):
        self.post("/v1/requests", {"work_key": "reviewed"})
        self.service.operator_display = lambda _text, _digest: False
        with self.assertRaisesRegex(LaunchError, "approval_denied"):
            self.service.review("req-1")
        self.assertTrue(self.authority.denied)
        self.assertEqual(self.ceremonies, [])
        self.assertEqual(self.dispatches, [])

    def test_fixed_dispatch_rejects_changed_task_after_grant_redemption(self):
        with TemporaryDirectory() as private:
            snapshot = Path(private) / "snapshot.json"
            snapshot.write_text("{}", encoding="utf-8")
            dispatch = object.__new__(LocalSavedFlowDispatch)
            dispatch.snapshot_path = snapshot
            dispatch.work_key = "github:S-20"
            dispatch.flow_id = "fixed-flow"
            dispatch.client = type("Client", (), {"fetch": lambda _self, _id: {}})()
            dispatch.run_path = Path(private) / "runs.sqlite3"
            dispatch.source_root = None
            authority = type("Authority", (), {
                "path": Path(private) / "approval.sqlite3",
                "__call__": lambda _self, _ref, _binding: {
                    "task_digest": "sha256:" + sha256(b"reviewed task").hexdigest()}})()
            launches = []

            def fake_launch(**kwargs):
                grant = kwargs["grant_authority"]("grant-1", {})
                launches.append((grant, kwargs["inputs"]))
                return ({"run_id": "r", "trace_id": "t", "status": "completed",
                         "dispatch_attempts": 1, "graph_revision": "g"}, "output")

            with patch("laomedo.work_graph.model.GraphSnapshot.from_dict",
                       return_value=object()), patch(
                       "laomedo.work_graph.launch.launch_github_docker_saved_flow_stage",
                       side_effect=fake_launch):
                with self.assertRaisesRegex(LaunchError, "grant_task_mismatch"):
                    dispatch("grant-1", {"task": "changed task", "choice": None}, authority)
                self.assertEqual(launches, [])
                result = dispatch("grant-1", {"task": "reviewed task", "choice": None}, authority)
                self.assertEqual(result["status"], "completed")
                self.assertEqual(launches[0][1], [{"input_value": "reviewed task"}])
