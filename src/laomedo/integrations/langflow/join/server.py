"""Implementation owned by integrations / langflow / join / server."""

from __future__ import annotations
from hmac import compare_digest
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit
import json
import laomedo.work_graph.runs.errors as _workflow_errors


class JoinServer(ThreadingHTTPServer):
    def __init__(self, controller, token, *, port, host="127.0.0.1"):
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
                return {
                    "client_request_id": snapshot["client_request_id"],
                    "request_hash": snapshot["runner_request_hash"],
                    "run_id": snapshot["runner_run_id"],
                    "laomedo_run_id": snapshot["run_id"],
                    "trace_id": snapshot["trace_id"],
                    "invocation_id": snapshot["invocation_id"],
                    "provider": snapshot["runner_provider"] or controller.provider,
                    "raw_event_ref": snapshot["runner_raw_event_ref"],
                    "status": (
                        "incomplete"
                        if snapshot.get("native_status") == "cancelled"
                        and snapshot.get("cancel_confirmed") is not True
                        else snapshot.get("native_status") or snapshot["status"]
                    ),
                    "native_status": snapshot.get("native_status"),
                    "cancel_requested": snapshot.get("cancel_requested", False),
                    "cancel_confirmed": snapshot.get("cancel_confirmed", False),
                    "executing_graph_verified": False,
                    "answer": native.get("answer"),
                    "activity_initial_attempt_id": native.get(
                        "activity_initial_attempt_id"
                    ),
                    "activity_attempt_id": native.get("activity_attempt_id"),
                    "attempt_finished": native.get("attempt_finished", False),
                    "snapshot_ready": native.get("snapshot_ready", False),
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
                    "error_category": native.get("error_category"),
                }

            def execute(self, action):
                if not self.authorized():
                    return
                try:
                    action()
                except _workflow_errors.LaunchError as exc:
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
                path = urlsplit(self.path)
                if path.query or path.fragment:
                    self.reply(404, {"error_category": "unknown_route"})
                    return

                def perform():
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 65536:
                        raise _workflow_errors.LaunchError("invalid_join_body")
                    try:
                        payload = json.loads(self.rfile.read(length))
                    except (ValueError, TypeError):
                        raise _workflow_errors.LaunchError(
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
                            raise _workflow_errors.LaunchError("invalid_join_body")
                        snapshot = controller.start(**payload)
                        self.reply(202, self.presented(snapshot))
                        return
                    parts = path.path.strip("/").split("/")
                    if (
                        len(parts) == 4
                        and parts[:2] == ["v1", "requests"]
                        and parts[3] == "cancel"
                        and payload == {}
                    ):
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
                        binding = controller.store.langflow_runner_binding(
                            parts[2], provider=controller.provider
                        )
                        if binding is None:
                            self.reply(404, {"error_category": "unknown_run"})
                            return
                        self.reply(
                            200,
                            self.presented(
                                controller.status(binding["client_request_id"])
                            ),
                        )
                        return
                    self.reply(404, {"error_category": "unknown_route"})

                self.execute(perform)

        super().__init__((host, port), Handler)
