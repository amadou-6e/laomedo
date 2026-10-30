"""Module-level private loopback request handling; protocol behavior is unchanged."""

from http.server import BaseHTTPRequestHandler
import json
import secrets
from laomedo.github.issues.contract import ERROR_CODES, PRE_DISPATCH_ERRORS
from laomedo.host.mediation.errors import KnownRejected


class IssueRequestHandler(BaseHTTPRequestHandler):
    """Authenticate and route one request using only its server instance bindings."""
    def log_message(self, *_):
        pass

    def reply(self, status, value):
        data = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if not secrets.compare_digest(
            self.headers.get("Authorization", ""), "Bearer " + self.server._token
        ):
            self.reply(401, {"error_category": "unauthorized"})
            return
        executing_write = False
        try:
            if (
                self.headers.get("Content-Type", "").split(";")[0]
                != "application/json"
            ):
                raise ValueError("invalid_request")
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 1024 * 1024:
                raise ValueError("invalid_request")
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError("invalid_request")
            if self.path == "/v1/github-issues/discover" and set(body) == {
                "repository_url",
                "labels",
                "state",
            }:
                result = self.server.gateway.discover(**body)
            elif self.path == "/v1/github-issues/execute" and set(body) == {
                "repository_url",
                "labels",
                "state",
                "issue_number",
                "operation",
            }:
                executing_write = bool(body["operation"])
                result = self.server.gateway.execute(**body)
            else:
                raise ValueError("invalid_request")
            self.reply(200, result)
        except Exception as error:
            category = (
                str(error)
                if type(error) is ValueError
                and str(error) in ERROR_CODES
                else "github_issue_unavailable"
            )
            if isinstance(
                error, KnownRejected
            ) and error.code in {
                "github_http_401",
                "github_http_403",
                "github_http_404",
                "github_http_410",
            }:
                category = error.code
            if (
                executing_write
                and category not in PRE_DISPATCH_ERRORS
            ):
                self.reply(503, {"error_category": "issue_write_unknown"})
            else:
                self.reply(400, {"error_category": category})
