"""Service-facing Work Graph approval API.

Only submit and launch are exposed to ordinary clients. Review and the
authenticator ceremony are invoked inside the service process. OS account and
Docker Engine isolation remain required before this can enforce #95.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from hashlib import sha256
import json
from pathlib import Path
import re

from laomedo.workflow_run_store import LaunchError


MAX_BODY_BYTES = 65536


class ApprovalService:
    def __init__(self, authority, *, operator_display, authenticator, dispatch):
        self.authority = authority
        self.operator_display = operator_display
        self.authenticator = authenticator
        self.dispatch = dispatch

    def submit(self, request):
        submitted = self.authority.submit(request)
        # A client cannot start its own ceremony with a returned challenge.
        return {"request_id": submitted["request_id"],
                "request_digest": submitted["request_digest"],
                "state": "pending"}

    def review(self, request_id):
        """Run only on the protected operator side, never from an API route."""
        pending = self.authority.pending_request(request_id)
        displayed = json.dumps(pending["request"], sort_keys=True, indent=2,
                               ensure_ascii=True)
        if not self.operator_display(displayed, pending["request_digest"]):
            self.authority.deny(request_id)
            raise LaunchError("approval_denied")
        assertion = self.authenticator(
            pending["challenge"], self.authority.anchor.rp_id,
            self.authority.anchor.origin)
        return self.authority.approve(request_id, assertion)

    def launch(self, grant_id, payload):
        """The fixed dispatch callback performs source checks and redemption."""
        return self.dispatch(grant_id, payload, self.authority)


class LocalSavedFlowDispatch:
    """Fixed service-owned launch configuration; HTTP clients supply no paths."""

    def __init__(self, *, snapshot_path, work_key, flow_id, langflow_base,
                 run_store, source_root=None):
        from .grants import _private_path
        from .local_launch import LangflowLocalClient
        self.snapshot_path = Path(snapshot_path).resolve()
        self.work_key = work_key
        self.flow_id = flow_id
        self.client = LangflowLocalClient(langflow_base)
        self.run_path = _private_path(run_store)
        self.source_root = source_root

    def __call__(self, grant_id, payload, authority):
        from .launch import launch_github_docker_saved_flow_stage
        from .model import GraphSnapshot
        from laomedo.workflow_run_store import WorkflowRunStore
        if (not isinstance(payload, dict) or set(payload) != {"task", "choice"} or
                not isinstance(payload["task"], str) or
                not 0 < len(payload["task"]) <= 100000 or
                payload["choice"] not in (None, "pinned", "refreshed")):
            raise LaunchError("approval_launch_payload_invalid")
        if self.run_path == authority.path:
            raise LaunchError("run_and_grant_store_must_differ")
        task = payload["task"]
        digest = "sha256:" + sha256(task.encode("utf-8")).hexdigest()

        def task_bound_authority(ref, binding):
            grant = authority(ref, binding)
            if grant.get("task_digest") != digest:
                raise LaunchError("grant_task_mismatch")
            return grant

        frozen = GraphSnapshot.from_dict(json.loads(
            self.snapshot_path.read_text(encoding="utf-8")))
        record, output = launch_github_docker_saved_flow_stage(
            frozen=frozen, work_key=self.work_key, flow_id=self.flow_id,
            fetch_export=self.client.fetch, store=WorkflowRunStore(self.run_path),
            grant_ref=grant_id, grant_authority=task_bound_authority,
            resolved_config={"mode": "approved-local"},
            choice=payload["choice"], inputs=[{"input_value": task}],
            types=["chat"], outputs=None, source_root=self.source_root)
        return {"run_id": record["run_id"], "trace_id": record["trace_id"],
                "status": record["status"], "dispatch_attempts": record["dispatch_attempts"],
                "output_present": bool(output), "graph_revision": record["graph_revision"]}


def make_http_handler(service):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format, *_args):
            pass

        def do_POST(self):
            if self.path not in ("/v1/requests", "/v1/launch"):
                self.send_error(404)
                return
            try:
                if self.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/json":
                    raise ValueError
                length = int(self.headers.get("Content-Length", ""))
                if not 0 < length <= MAX_BODY_BYTES:
                    raise ValueError
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError
                if self.path == "/v1/requests":
                    result = service.submit(body)
                else:
                    if set(body) != {"grant_id", "payload"}:
                        raise ValueError
                    result = service.launch(body["grant_id"], body["payload"])
                encoded = json.dumps(result, sort_keys=True).encode("utf-8")
                self.send_response(200)
            except (ValueError, TypeError, KeyError):
                encoded = b'{"error":"invalid_request"}'
                self.send_response(400)
            except LaunchError as exc:
                reason = str(exc)
                if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", reason):
                    reason = "launch_refused"
                encoded = json.dumps({"error": reason}).encode("utf-8")
                self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return Handler


def serve_loopback(service, port=0):
    """Build a loopback server; the caller owns its process and OS identity."""
    return ThreadingHTTPServer(("127.0.0.1", port), make_http_handler(service))
