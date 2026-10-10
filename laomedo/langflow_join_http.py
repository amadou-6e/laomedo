"""Opt-in local HTTP boundary for a host-owned Langflow join controller.

The caller supplies the bridge token, saved-flow resolver and runner transport.
This module does not start a service or alter an existing Langflow installation.
"""

from hmac import compare_digest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from urllib import error, request
from urllib.parse import urlsplit

from .workflow_run_store import LaunchError


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *_):
        return None


class RunnerHTTPTransport:
    """Authenticated host-side client for the existing local Codex runner."""

    def __init__(self, base_url, token, *, timeout=30):
        parsed = urlsplit(str(base_url).rstrip("/"))
        if (parsed.scheme != "http" or parsed.hostname not in
                {"127.0.0.1", "localhost", "::1"} or parsed.username or
                parsed.password or parsed.path or parsed.query or parsed.fragment):
            raise ValueError("local_runner_url_required")
        if not isinstance(token, str) or not token or not 1 <= timeout <= 120:
            raise ValueError("runner_transport_config_invalid")
        self.base_url = str(base_url).rstrip("/")
        self.token = token
        self.timeout = timeout
        self.opener = request.build_opener(_NoRedirect())

    def _call(self, method, path, payload=None):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = request.Request(self.base_url + path, data=body, method=method,
            headers={"Authorization": "Bearer " + self.token,
                     "Content-Type": "application/json"})
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                if int(response.headers.get("Content-Length", "0") or 0) > 1048576:
                    raise RuntimeError("runner_response_too_large")
                raw = response.read(1048577)
        except error.HTTPError as exc:
            if method == "GET" and exc.code == 404 and path.startswith("/v1/requests/"):
                raise LookupError("request_not_found") from None
            raise RuntimeError("runner_http_rejected") from None
        except (error.URLError, TimeoutError, OSError):
            raise RuntimeError("runner_transport_unknown") from None
        if len(raw) > 1048576:
            raise RuntimeError("runner_response_too_large")
        try:
            value = json.loads(raw)
        except (ValueError, TypeError):
            raise RuntimeError("runner_invalid_response") from None
        if not isinstance(value, dict):
            raise RuntimeError("runner_invalid_response")
        return value

    def start_async(self, body):
        return self._call("POST", "/v1/runs/async", body)

    def lookup_request(self, request_id):
        return self._call("GET", "/v1/requests/" + str(request_id))

    def status(self, run_id):
        return self._call("GET", "/v1/runs/" + str(run_id))

    def cancel(self, run_id):
        return self._call("POST", "/v1/runs/" + str(run_id) + "/cancel", {})


def serve_langflow_join(controller, token, *, port, host="127.0.0.1"):
    """Construct an authenticated bridge; caller owns its lifecycle."""
    if not isinstance(token, str) or not token or not 0 <= port <= 65535:
        raise ValueError("join_server_config_invalid")
    if host != "127.0.0.1":
        raise ValueError("join_server_must_bind_loopback")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            return

        def reply(self, code, value):
            data = json.dumps(value, sort_keys=True).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def authorized(self):
            received = self.headers.get("Authorization", "")
            if not compare_digest(received, "Bearer " + token):
                self.reply(401, {"error_category": "unauthorized"})
                return False
            return True

        @staticmethod
        def presented(snapshot):
            if snapshot is None:
                return {"status": "pending_start"}
            native = snapshot.get("native_record") or {}
            return {"client_request_id": snapshot["client_request_id"],
                    "request_hash": snapshot["runner_request_hash"],
                    "run_id": snapshot["runner_run_id"],
                    "laomedo_run_id": snapshot["run_id"],
                    "trace_id": snapshot["trace_id"],
                    "invocation_id": snapshot["invocation_id"],
                    "provider": snapshot["runner_provider"] or "codex",
                    "raw_event_ref": snapshot["runner_raw_event_ref"],
                    "status": snapshot.get("native_status") or snapshot["status"],
                    "cancel_requested": snapshot.get("cancel_requested", False),
                    "cancel_confirmed": snapshot.get("cancel_confirmed", False),
                    "executing_graph_verified": False,
                    "answer": native.get("answer"),
                    "thread_id": native.get("thread_id"),
                    "post_run_hash": native.get("post_run_hash"),
                    "requested_model": native.get("requested_model"),
                    "requested_effort": native.get("requested_effort"),
                    "skill": native.get("skill"),
                    "skills": native.get("skills"),
                    "output_ref": native.get("output_ref"),
                    "handoff": native.get("handoff"),
                    "imported_artifacts": native.get("imported_artifacts", []),
                    "usage": native.get("usage"),
                    "error_category": native.get("error_category")}

        def execute(self, action):
            if not self.authorized():
                return
            try:
                action()
            except LaunchError as exc:
                category = str(exc)
                code = 409 if category in {
                    "client_request_identity_conflict", "client_request_binding_conflict",
                    "runner_ack_identity_mismatch", "runner_binding_conflict",
                    "runner_lookup_mismatch"} else 502 if category in {
                    "runner_start_unknown", "runner_status_unknown",
                    "runner_lookup_unknown"} else 400
                self.reply(code, {"error_category": category})
            except Exception:
                self.reply(502, {"error_category": "join_backend_unknown"})

        def do_POST(self):
            path = urlsplit(self.path)
            if path.query or path.fragment:
                self.reply(404, {"error_category": "unknown_route"})
                return
            def perform():
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536:
                    raise LaunchError("invalid_join_body")
                try:
                    payload = json.loads(self.rfile.read(length))
                except (ValueError, TypeError):
                    raise LaunchError("invalid_join_body") from None
                if path.path == "/v1/invocations":
                    if not isinstance(payload, dict) or set(payload) != {
                        "client_request_id", "flow_id", "graph_run_id",
                        "stage_id", "runner_body"}:
                        raise LaunchError("invalid_join_body")
                    snapshot = controller.start(**payload)
                    self.reply(202, self.presented(snapshot))
                    return
                parts = path.path.strip("/").split("/")
                if (len(parts) == 4 and parts[:2] == ["v1", "requests"] and
                        parts[3] == "cancel" and payload == {}):
                    snapshot = controller.cancel(parts[2])
                    if snapshot.get("status") == "pending_start":
                        self.reply(202, snapshot)
                    else:
                        self.reply(202, self.presented(controller.status(parts[2])))
                    return
                self.reply(404, {"error_category": "unknown_route"})
            self.execute(perform)

        def do_GET(self):
            path = urlsplit(self.path)
            if path.query or path.fragment:
                self.reply(404, {"error_category": "unknown_route"})
                return
            def perform():
                parts = path.path.strip("/").split("/")
                if len(parts) == 3 and parts[:2] == ["v1", "requests"]:
                    snapshot = controller.status(parts[2])
                    self.reply(200, self.presented(snapshot) if snapshot else
                               {"client_request_id": parts[2],
                                "status": "pending_start"})
                    return
                if len(parts) == 3 and parts[:2] == ["v1", "runs"]:
                    binding = controller.store.langflow_runner_binding(parts[2])
                    if binding is None:
                        self.reply(404, {"error_category": "unknown_run"})
                        return
                    self.reply(200, self.presented(
                        controller.status(binding["client_request_id"])))
                    return
                self.reply(404, {"error_category": "unknown_route"})
            self.execute(perform)

    return ThreadingHTTPServer((host, port), Handler)
