"""Authenticated Claude command/mediation adaptation, separate from execution."""

import json
import secrets
import threading
from uuid import uuid4
from laomedo.agents.agents.claude.http.server import CommandHttpServer
from laomedo.agents.agents.base.models.commands import CommandRequest
from laomedo.agents.errors import RunnerError


class ClaudeCommandTransport:
    """Own one private HTTP capability and project native wire requests/results."""

    def __init__(self, executor):
        """Start the existing loopback listener and private capability file."""
        self.executor = executor
        self.token = secrets.token_hex(32)
        self.server = CommandHttpServer(self, ("127.0.0.1", 0))
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.secret_path = executor.root / ("command-capability-" + uuid4().hex)
        try:
            self.thread.start()
            self.secret_path.write_text(self.token, encoding="ascii")
        except BaseException:
            # A failed capability write must not strand an active listener.
            if self.thread.is_alive():
                self.server.shutdown()
                self.thread.join(timeout=3)
            self.server.server_close()
            self.secret_path.unlink(missing_ok=True)
            if self.thread.is_alive():
                raise RunnerError("container_termination_unverified") from None
            raise
        self.url = f"http://host.docker.internal:{self.server.server_port}/command"

    def execute(self, value):
        """Admit the existing wire shape before invoking typed command execution."""
        if (
            not isinstance(value, dict)
            or set(value) != {"command"}
            or not isinstance(value["command"], str)
        ):
            raise RunnerError("claude_workspace_command_invalid")
        if not value["command"].strip() or len(value["command"]) > 60000:
            raise RunnerError("claude_workspace_command_invalid")
        result = self.executor.execute(CommandRequest(command=value["command"]))
        return {"exit_code": result.exit_code, "output": result.stdout}

    def mediate(self, value):
        """Forward one admitted effect to the existing host mediator; unknown outcomes stop commands and are never resent."""
        from urllib.request import Request
        from urllib.request import ProxyHandler, build_opener
        from laomedo.http.redirect import NoRedirect
        from urllib.error import HTTPError

        if (
            self.executor.mediation is None
            or self.executor.closed
            or self.executor.cancelled.is_set()
        ):
            raise RunnerError("mediated_grant_unavailable")
        if (
            not isinstance(value, dict)
            or set(value) - {"operation", "payload", "effect_id"}
            or not isinstance(value.get("operation"), str)
            or not isinstance(value.get("payload"), dict)
        ):
            raise RunnerError("claude_workspace_command_invalid")
        url, instance, secret_path = self.executor.mediation
        body = {
            **value,
            "repository": self.executor.record["github_scope"]["repository"],
        }
        request = Request(
            url.replace("host.docker.internal", "127.0.0.1"),
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + secret_path.read_text().strip(),
                "X-Laomedo-Mediator-Instance": instance,
            },
        )
        try:
            with build_opener(ProxyHandler({}), NoRedirect()).open(
                request, timeout=20
            ) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code in {400, 401, 403, 404, 409, 422}:
                # An authoritative refusal contains no raw response. A redirect
                # or server failure does not establish whether an effect ran.
                return {"error": "mediation_request_refused"}
        except Exception:
            pass
        self.executor.record["mediation_outcome"] = "unknown"
        self.executor.cancelled.set()
        raise RunnerError("claude_mediation_outcome_unknown") from None

    def close(self):
        """Revoke admission, stop the listener and wait for owned command cleanup."""
        self.executor.closed = True
        self.executor.stopping.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        with self.executor.lock:
            self.secret_path.unlink(missing_ok=True)
        if self.executor.cleanup_failed or self.thread.is_alive():
            raise RunnerError("container_termination_unverified")
