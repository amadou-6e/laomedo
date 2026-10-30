"""Authenticated join HTTP adapter; values come from leaf interface models."""
from hmac import compare_digest
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit
import json
from laomedo.agents.interface.models import RunnerStatusRecord
from laomedo.work_graph.runs.errors import LaunchError


class JoinRequestHandler(BaseHTTPRequestHandler):
    """Adapt authenticated HTTP calls to the explicitly owned join controller."""

    def log_message(self, *_):
        """Keep authorization and request metadata out of the default access log."""
        return

    def reply(self, code, value):
        """Write the existing sorted JSON response with its exact byte length."""
        data = json.dumps(value, sort_keys=True).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def authorized(self):
        """Admit only the server's exact bearer credential without disclosing it."""
        received = self.headers.get("Authorization", "")
        if not compare_digest(received, "Bearer " + self.server.token):
            self.reply(401, {"error_category": "unauthorized"})
            return False
        return True

    def presented(self, snapshot):
        """Preserve the runner-status contract, independent of graph output."""
        return RunnerStatusRecord.from_snapshot(snapshot, provider=self.server.controller.provider).to_payload()

    def execute(self, action):
        """Keep conflict and uncertain-run errors distinct from rejected input."""
        if not self.authorized():
            return
        try:
            action()
        except LaunchError as exc:
            category = str(exc)
            code = (
                409
                if category
                in {
                    "client_request_identity_conflict",
                    "client_request_binding_conflict",
                    "runner_ack_identity_mismatch",
                    "runner_binding_conflict",
                    "runner_lookup_mismatch",
                }
                else (
                    502
                    if category
                    in {
                        "runner_start_unknown",
                        "runner_status_unknown",
                        "runner_lookup_unknown",
                    }
                    else 400
                )
            )
            self.reply(code, {"error_category": category})
        except Exception:
            self.reply(502, {"error_category": "join_backend_unknown"})

    def do_POST(self):
        """Dispatch the existing bounded invocation/cancel HTTP routes."""
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
                raise LaunchError(
                    "invalid_join_body"
                ) from None
            if path.path == "/v1/invocations":
                if not isinstance(payload, dict) or set(payload) != {
                    "client_request_id",
                    "flow_id",
                    "graph_run_id",
                    "stage_id",
                    "runner_body",
                }:
                    raise LaunchError("invalid_join_body")
                snapshot = self.server.controller.start(**payload)
                self.reply(202, self.presented(snapshot))
                return
            parts = path.path.strip("/").split("/")
            if (
                len(parts) == 4
                and parts[:2] == ["v1", "requests"]
                and parts[3] == "cancel"
                and payload == {}
            ):
                snapshot = self.server.controller.cancel(parts[2])
                if snapshot.get("status") == "pending_start":
                    self.reply(202, snapshot)
                else:
                    self.reply(202, self.presented(self.server.controller.status(parts[2])))
                return
            self.reply(404, {"error_category": "unknown_route"})

        self.execute(perform)

    def do_GET(self):
        """Read existing request/run status without creating a model request."""
        path = urlsplit(self.path)
        if path.query or path.fragment:
            self.reply(404, {"error_category": "unknown_route"})
            return

        def perform():
            parts = path.path.strip("/").split("/")
            if len(parts) == 3 and parts[:2] == ["v1", "requests"]:
                snapshot = self.server.controller.status(parts[2])
                self.reply(
                    200,
                    (
                        self.presented(snapshot)
                        if snapshot
                        else {
                            "client_request_id": parts[2],
                            "status": "pending_start",
                        }
                    ),
                )
                return
            if len(parts) == 3 and parts[:2] == ["v1", "runs"]:
                binding = self.server.controller.store.langflow_runner_binding(
                    parts[2], provider=self.server.controller.provider
                )
                if binding is None:
                    self.reply(404, {"error_category": "unknown_run"})
                    return
                self.reply(
                    200,
                    self.presented(
                        self.server.controller.status(binding["client_request_id"])
                    ),
                )
                return
            self.reply(404, {"error_category": "unknown_route"})

        self.execute(perform)
