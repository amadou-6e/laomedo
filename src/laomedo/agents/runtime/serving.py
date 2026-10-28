"""Expose the authenticated local runner HTTP interface."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import laomedo.agents.runtime.runner as _runtime_runner
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
import json
import laomedo.agents.artifacts.errors as _artifacts_errors
import laomedo.agents.runtime.settings as _runtime_settings
import laomedo.agents.runtime.errors as _runtime_errors
import laomedo.agents.runtime.utils as _runtime_utils
import laomedo.skills.registry.errors as _registry_errors
import os
import secrets
import threading


class RunnerServer(ThreadingHTTPServer):
    def __init__(
        self,
        runner: _runtime_runner.LocalRunner,
        host: str = "127.0.0.1",
        port: int = 8765,
    ):
        import laomedo.agents.runtime.runner as _runtime_runner

        if host not in ("127.0.0.1", "::1"):
            raise _runtime_errors.RunnerError("loopback_only")

        class Handler(BaseHTTPRequestHandler):
            def _reply(self, code: int, value: dict):
                data = json.dumps(value).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _body(self):
                if (
                    self.headers.get("Content-Type", "")
                    .split(";", 1)[0]
                    .strip()
                    .lower()
                    != "application/json"
                ):
                    raise _runtime_errors.RunnerError("json_content_type_required")
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > _runtime_settings.MAX_BODY:
                    raise _runtime_errors.RunnerError("invalid_body_size")
                return json.loads(self.rfile.read(length))

            def _authorized(self):
                supplied = self.headers.get("Authorization", "")
                if not secrets.compare_digest(supplied, "Bearer " + runner.api_token):
                    self._reply(
                        401, {"status": "failed", "error_category": "unauthorized"}
                    )
                    return False
                return True

            def do_GET(self):
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
                            (
                                runner.model_catalog(refresh=True)
                                if getattr(runner, "provider", "codex") == "claude"
                                else runner.model_catalog()
                            ),
                        )
                        return
                    if parts == ["v1", "health"]:
                        self._reply(
                            200,
                            {
                                "status": "ready",
                                "provider": getattr(runner, "provider", "codex"),
                            },
                        )
                        return
                    if (
                        len(parts) == 4
                        and parts[:2] == ["v1", "runs"]
                        and parts[3] == "events"
                    ):
                        import laomedo.activity.runner.feed as _runner_feed

                        query = parse_qs(parsed.query)
                        record = runner.status(parts[2])
                        attempt_id = query.get("attempt", [""])[0]
                        attempt_path = (
                            runner._run_dir(parts[2])
                            / "activity-attempts"
                            / (_runtime_utils._id(attempt_id) + ".json")
                            if attempt_id
                            else None
                        )
                        attempt = (
                            _runtime_utils._read(attempt_path)
                            if attempt_path and attempt_path.is_file()
                            else None
                        )
                        if not attempt:
                            self._reply(
                                200,
                                {"run_id": parts[2], "accepted": False, "events": []},
                            )
                            return
                        if attempt.get("id") != attempt_id:
                            raise _runtime_errors.RunnerError(
                                "activity_attempt_identity_mismatch"
                            )
                        boundary = (
                            attempt if attempt.get("native_end") is not None else None
                        )
                        native_after = max(
                            int(query.get("after", ["0"])[0]), attempt["native_start"]
                        )
                        otel_after = max(
                            int(query.get("otel_after", ["0"])[0]),
                            attempt["otel_start"],
                        )
                        feed = _runner_feed.read_feed(
                            runner._run_dir(parts[2]) / "activity-events.jsonl",
                            after=native_after,
                            limit=int(query.get("limit", ["100"])[0]),
                            tail=query.get("tail", ["0"])[0] == "1",
                            before=boundary["native_end"] if boundary else None,
                        )
                        telemetry = _runner_feed.read_feed(
                            runner._run_dir(parts[2]) / "otel-events.jsonl",
                            after=otel_after,
                            limit=200,
                            tail=query.get("tail", ["0"])[0] == "1",
                            before=boundary["otel_end"] if boundary else None,
                        )
                        self._reply(
                            200,
                            {
                                **feed,
                                "run_id": parts[2],
                                "accepted": True,
                                "attempt": attempt,
                                "telemetry": telemetry,
                                "closed_boundary": boundary,
                                "status": record.get("status"),
                                "thread_id": record.get("thread_id"),
                                "model": record.get("effective_model"),
                                "attempt_finished": record.get(
                                    "attempt_finished", False
                                ),
                            },
                        )
                        return
                    if len(parts) != 3:
                        raise _runtime_errors.RunnerError("unknown_endpoint")
                    if parts[:2] == ["v1", "runs"]:
                        result = runner.status(parts[2])
                    elif parts[:2] == ["v1", "requests"]:
                        result = runner.lookup_request(parts[2])
                    else:
                        raise _runtime_errors.RunnerError("unknown_endpoint")
                    self._reply(200, result)
                except (_runtime_errors.RunnerError, ValueError, OSError) as exc:
                    category = str(exc)
                    code = (
                        409
                        if category == "request_identity_conflict"
                        else 400 if category == "invalid_request_id" else 404
                    )
                    self._reply(code, {"status": "failed", "error_category": category})

            def do_POST(self):
                if not self._authorized():
                    return
                response_gate = None
                try:
                    parts = self.path.strip("/").split("/")
                    body = self._body()
                    is_cancel_endpoint = (
                        len(parts) == 4
                        and parts[:2] == ["v1", "runs"]
                        and parts[3] == "cancel"
                    )
                    if parts == ["v1", "runs", "async"]:
                        response_gate = threading.Event()
                        result = runner.start_async(body, response_gate=response_gate)
                        self._reply(202, result)
                        return
                    if parts == ["v1", "runs"]:
                        result = runner.start(body)
                    elif (
                        len(parts) == 4
                        and parts[:2] == ["v1", "runs"]
                        and parts[3] == "resume"
                    ):
                        extra = {}
                        if (
                            getattr(runner, "provider", "codex") == "claude"
                            and "run_timeout_seconds" in body
                        ):
                            value = body["run_timeout_seconds"]
                            if type(value) is not int or not 1 <= value <= 86400:
                                raise _runtime_errors.RunnerError(
                                    "claude_turn_timeout_invalid"
                                )
                            extra["run_timeout_seconds"] = value
                        if getattr(runner, "provider", "codex") == "claude":
                            required = (
                                extra["run_timeout_seconds"]
                                if extra
                                else runner.status(parts[2]).get(
                                    "turn_timeout", runner.turn_timeout
                                )
                            )
                            runner._mirror_host_login(minimum_validity_seconds=required)
                        else:
                            runner._mirror_host_login()
                        result = runner.resume(
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
                        len(parts) == 4
                        and parts[:2] == ["v1", "runs"]
                        and parts[3] == "cancel"
                    ):
                        result = runner.cancel(parts[2])
                    elif (
                        len(parts) == 4
                        and parts[:2] == ["v1", "runs"]
                        and parts[3] == "publish"
                    ):
                        if body != {}:
                            raise _runtime_errors.RunnerError(
                                "publication_body_must_be_empty"
                            )
                        result = runner.publish(parts[2])
                    elif (
                        len(parts) == 4
                        and parts[:2] == ["v1", "runs"]
                        and parts[3] == "artifacts"
                    ):
                        result = {
                            "status": "completed",
                            "artifact_refs": runner.select_artifacts(
                                parts[2], body["paths"]
                            ),
                        }
                    else:
                        raise _runtime_errors.RunnerError("unknown_endpoint")
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
                                or (
                                    is_cancel_endpoint
                                    and result["status"] == "cancelled"
                                )
                                else 502
                            )
                        )
                    )
                    self._reply(code, result)
                except (
                    _runtime_errors.RunnerError,
                    _registry_errors.SkillStoreError,
                    _artifacts_errors.ArtifactError,
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

        gate = os.environ.get("LAOMEDO_STARTUP_GATE")
        if gate:
            import laomedo.host.runner.startup as _runner_startup

            with _runner_startup.startup_gate(gate) as listening:
                if listening.with_suffix(".cancel").exists():
                    listening.with_suffix(".cancelled").touch()
                    raise SystemExit(0)
                super().__init__((host, port), Handler)
                listening.touch()
                return
        super().__init__((host, port), Handler)
