"""Module-level request handling preserving the existing local HTTP contract."""

from __future__ import annotations

from typing import TYPE_CHECKING
from http.server import BaseHTTPRequestHandler
import json
import secrets
import threading

from laomedo.agents.artifacts.errors import ArtifactError
from laomedo.agents.agents.base.settings import MAX_BODY
from laomedo.agents.errors import RunnerError
from laomedo.skills.registry.errors import SkillStoreError

if TYPE_CHECKING:
    from .server import RunnerServer


class RunnerRequestHandler(BaseHTTPRequestHandler):
    """Handle the existing wire protocol through this server's explicit owner."""

    server: "RunnerServer"

    def do_GET(self):
        """Authenticate and serve the existing metadata and retained-run read routes."""
        if not self._authorized():
            return
        try:
            from urllib.parse import urlsplit
            from urllib.parse import parse_qs

            parsed = urlsplit(self.path)
            parts = parsed.path.strip("/").split("/")
            if parts == ["v1", "models"] and not parsed.query:
                self._reply(
                    200,
                    self.server.runner.editor_model_catalog(),
                )
                return
            if parts == ["v1", "health"]:
                self._reply(
                    200,
                    {
                        "status": "ready",
                        "provider": self.server.runner.provider,
                    },
                )
                return
            if (
                len(parts) == 4
                and parts[:2] == ["v1", "runs"]
                and parts[3] == "activity"
            ):
                query = parse_qs(parsed.query)
                try:
                    after = int(query.get("after", ["0"])[0])
                    limit = int(query.get("limit", ["100"])[0])
                except ValueError:
                    raise RunnerError("invalid_activity_cursor") from None
                page = self.server.runner.read_activity(
                    parts[2], query.get("attempt", [""])[0], after=after, limit=limit
                )
                self._reply(200, page.to_payload())
                return
            if len(parts) == 4 and parts[:2] == ["v1", "runs"] and parts[3] == "events":
                query = parse_qs(parsed.query)
                self._reply(
                    200,
                    self.server.runner.read_events(
                        parts[2],
                        query.get("attempt", [""])[0],
                        after=int(query.get("after", ["0"])[0]),
                        otel_after=int(query.get("otel_after", ["0"])[0]),
                        limit=int(query.get("limit", ["100"])[0]),
                        tail=query.get("tail", ["0"])[0] == "1",
                    ),
                )
                return
            if len(parts) != 3:
                raise RunnerError("unknown_endpoint")
            if parts[:2] == ["v1", "runs"]:
                result = self.server.runner.status(parts[2])
            elif parts[:2] == ["v1", "requests"]:
                result = self.server.runner.lookup_request(parts[2])
            else:
                raise RunnerError("unknown_endpoint")
            self._reply(200, result)
        except (RunnerError, ValueError, OSError) as exc:
            category = str(exc)
            code = (
                409
                if category == "request_identity_conflict"
                else 400 if category == "invalid_request_id" else 404
            )
            self._reply(code, {"status": "failed", "error_category": category})

    def do_POST(self):
        """Authenticate and handle the existing request protocol, preserving wire errors."""
        if not self._authorized():
            return
        response_gate = None
        try:
            parts = self.path.strip("/").split("/")
            body = self._body()
            is_cancel_endpoint = (
                len(parts) == 4 and parts[:2] == ["v1", "runs"] and parts[3] == "cancel"
            )
            if parts == ["v1", "runs", "async"]:
                response_gate = threading.Event()
                result = self.server.runner.start_async(
                    body, response_gate=response_gate
                )
                self._reply(202, result)
                return
            if parts == ["v1", "runs"]:
                result = self.server.runner.start(body)
            elif (
                len(parts) == 4 and parts[:2] == ["v1", "runs"] and parts[3] == "resume"
            ):
                extra = self.server.runner.prepare_resume(parts[2], body)
                result = self.server.runner.resume(
                    parts[2],
                    body["task"],
                    expected_post_run_hash=body["expected_post_run_hash"],
                    expected_thread_id=body["expected_thread_id"],
                    model=body["model"],
                    effort=body["effort"],
                    activity_attempt_id=body.get("activity_attempt_id"),
                    **extra,
                )
            elif (
                len(parts) == 4 and parts[:2] == ["v1", "runs"] and parts[3] == "cancel"
            ):
                result = self.server.runner.cancel(parts[2])
            elif (
                len(parts) == 4
                and parts[:2] == ["v1", "runs"]
                and parts[3] == "publish"
            ):
                if body != {}:
                    raise RunnerError("publication_body_must_be_empty")
                result = self.server.runner.publish(parts[2])
            elif (
                len(parts) == 4
                and parts[:2] == ["v1", "runs"]
                and parts[3] == "artifacts"
            ):
                result = {
                    "status": "completed",
                    "artifact_refs": self.server.runner.select_artifacts(
                        parts[2], body["paths"]
                    ),
                }
            else:
                raise RunnerError("unknown_endpoint")
            is_publication_endpoint = (
                len(parts) == 4
                and parts[:2] == ["v1", "runs"]
                and parts[3] == "publish"
            )
            code = (
                200
                if is_publication_endpoint
                else (
                    202
                    if is_cancel_endpoint
                    and result.get("cancel_requested")
                    and not result.get("cancel_confirmed")
                    else (
                        200
                        if result["status"] == "completed"
                        or (is_cancel_endpoint and result["status"] == "cancelled")
                        else 502
                    )
                )
            )
            self._reply(code, result)
        except (
            RunnerError,
            SkillStoreError,
            ArtifactError,
            KeyError,
            ValueError,
            OSError,
        ) as exc:
            self._reply(
                409 if str(exc) == "request_identity_conflict" else 400,
                {"status": "failed", "error_category": str(exc)},
            )
        finally:
            if response_gate is not None:
                response_gate.set()

    def _reply(self, code: int, value: dict):
        """Serialize the response using the existing JSON status and content length."""
        data = json.dumps(value).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        """Read a bounded JSON body after validating its media type and declared size."""
        if (
            self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            != "application/json"
        ):
            raise RunnerError("json_content_type_required")
        length = int(self.headers.get("Content-Length", "0"))
        if length < 1 or length > MAX_BODY:
            raise RunnerError("invalid_body_size")
        return json.loads(self.rfile.read(length))

    def _authorized(self):
        """Check the configured bearer and send the existing rejection on mismatch."""
        supplied = self.headers.get("Authorization", "")
        if not secrets.compare_digest(
            supplied, "Bearer " + self.server.runner.api_token
        ):
            self._reply(401, {"status": "failed", "error_category": "unauthorized"})
            return False
        return True
