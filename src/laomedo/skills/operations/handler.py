"""Module-level private loopback request handling; protocol behavior is unchanged."""

from http.server import BaseHTTPRequestHandler
import json
import secrets


class SkillOperationRequestHandler(BaseHTTPRequestHandler):
    """Authenticate and route one request using only its server instance bindings."""

    def log_message(self, *_):
        pass

    def reply(self, status, value):
        data = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if not secrets.compare_digest(
            self.headers.get("Authorization", ""), "Bearer " + self.server._token
        ):
            self.reply(401, {"error_category": "unauthorized"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if (
                self.headers.get("Content-Type", "").split(";")[0] != "application/json"
                or not 0 < size <= 4 * 1024 * 1024
            ):
                raise ValueError("skill_request_invalid")
            body = json.loads(self.rfile.read(size))
            action = self.path.removeprefix("/v1/skill-operations/")
            fields = {
                "prepare": {"skill_id", "revision_id", "commit_id"},
                "apply": {"ticket", "operation", "editor"},
                "history": {"skill_id", "revision_id", "before"},
                "diff": {"skill_id", "commit_id"},
                "compare": {"skill_id", "commit_id", "revision_id"},
            }
            if (
                action not in fields
                or self.path != "/v1/skill-operations/" + action
                or not isinstance(body, dict)
                or set(body) != fields[action]
            ):
                raise ValueError("skill_request_invalid")
            self.reply(200, getattr(self.server.operations, action)(**body))
        except Exception:
            # Never disclose parser data, source paths, tickets or tracebacks.
            self.reply(400, {"error_category": "skill_operation_refused"})
