"""Credential-free tests of the opt-in local HTTP boundary."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from urllib import error, request
from uuid import uuid4

from laomedo.langflow_join import LangflowJoinController
from laomedo.langflow_join_http import RunnerHTTPTransport, serve_langflow_join
from laomedo.workflow_run_store import WorkflowRunStore
from tests.test_langflow_join_controller import FakeRunner


class LangflowJoinHTTPTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = WorkflowRunStore(Path(temporary.name) / "runs.sqlite3")
        self.runner = FakeRunner()
        flow = {"id": "saved-flow", "data": {"nodes": [{"id": "agent",
            "data": {"node": {"template": {"code": {"value": "synthetic code"}}}}}]}}
        self.controller = LangflowJoinController(
            self.store, self.runner, lambda _flow: flow)
        self.token = uuid4().hex
        self.server = serve_langflow_join(self.controller, self.token, port=0)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.base = "http://127.0.0.1:" + str(self.server.server_port)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def call(self, method, path, body=None, *, token=None):
        headers = {"Content-Type": "application/json"}
        if token is not False:
            headers["Authorization"] = "Bearer " + (token or self.token)
        req = request.Request(self.base + path,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=5) as response:
                return response.status, json.load(response)
        except error.HTTPError as exc:
            return exc.code, json.load(exc)

    @staticmethod
    def body(client):
        return {"client_request_id": client, "flow_id": "saved-flow",
                "graph_run_id": "reported-graph", "stage_id": "agent",
                "runner_body": {"task": "synthetic task", "model": "synthetic",
                                "effort": "low", "skill_ref": {"skill_id": "fixture"}}}

    def test_authenticated_start_retry_status_and_cancel(self):
        client = str(uuid4())
        body = self.body(client)
        self.assertEqual(self.call("POST", "/v1/invocations", body,
                                   token=False)[0], 401)
        code, started = self.call("POST", "/v1/invocations", body)
        self.assertEqual(code, 202)
        self.assertEqual(started["client_request_id"], client)
        self.assertIsNotNone(started["run_id"])
        self.assertFalse(started["executing_graph_verified"])
        self.assertEqual(len(self.runner.starts), 1)
        code, retry = self.call("POST", "/v1/invocations", body)
        self.assertEqual(code, 202)
        self.assertEqual(retry["run_id"], started["run_id"])
        self.assertEqual(len(self.runner.starts), 1)
        code, by_client = self.call("GET", "/v1/requests/" + client)
        self.assertEqual(code, 200)
        self.assertEqual(by_client["run_id"], started["run_id"])
        code, by_run = self.call("GET", "/v1/runs/" + started["run_id"])
        self.assertEqual(code, 200)
        self.assertEqual(by_run["invocation_id"], started["invocation_id"])
        code, cancelled = self.call("POST", "/v1/requests/" + client + "/cancel", {})
        self.assertEqual(code, 202)
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertTrue(cancelled["cancel_confirmed"])
        self.assertEqual(len(self.runner.cancels), 1)
        changed = self.body(client)
        changed["runner_body"]["task"] = "changed"
        self.assertEqual(self.call("POST", "/v1/invocations", changed)[0], 409)

    def test_stop_intent_before_start_refuses_native_call(self):
        client = str(uuid4())
        code, pending = self.call("POST", "/v1/requests/" + client + "/cancel", {})
        self.assertEqual(code, 202)
        self.assertEqual(pending["status"], "pending_start")
        code, cancelled = self.call("POST", "/v1/invocations", self.body(client))
        self.assertEqual(code, 202)
        self.assertIsNone(cancelled["run_id"])
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(self.runner.starts, [])

    def test_runner_redirect_does_not_forward_host_token(self):
        hits = []
        class Target(BaseHTTPRequestHandler):
            def log_message(self, *_):
                return
            def do_POST(self):
                hits.append(self.headers.get("Authorization"))
                self.send_response(200)
                self.end_headers()
        target = ThreadingHTTPServer(("127.0.0.1", 0), Target)
        target_thread = Thread(target=target.serve_forever, daemon=True)
        target_thread.start()
        class Redirect(BaseHTTPRequestHandler):
            def log_message(self, *_):
                return
            def do_POST(self):
                self.send_response(307)
                self.send_header("Location", "http://127.0.0.1:" +
                                 str(target.server_port) + "/capture")
                self.end_headers()
        redirect = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
        redirect_thread = Thread(target=redirect.serve_forever, daemon=True)
        redirect_thread.start()
        try:
            transport = RunnerHTTPTransport(
                "http://127.0.0.1:" + str(redirect.server_port), "dummy-secret")
            with self.assertRaisesRegex(RuntimeError,
                                        "runner_http_rejected|runner_transport_unknown"):
                transport.start_async({"request_id": str(uuid4()), "task": "synthetic"})
            self.assertEqual(hits, [])
        finally:
            redirect.shutdown()
            redirect.server_close()
            redirect_thread.join(timeout=3)
            target.shutdown()
            target.server_close()
            target_thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
