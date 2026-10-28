"""Loopback backend for live PR reads and existing scoped operation grants."""

from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from pathlib import Path
import argparse
import json
import laomedo.github.pull_requests.contract as _pull_requests_contract
import laomedo.github.pull_requests.gateway as _pull_requests_gateway
import laomedo.github.transport.rest.transport as _rest_transport
import laomedo.host.credentials.token.connection as _token_connection
import laomedo.host.mediation.errors as _mediation_errors
import laomedo.host.mediation.store as _mediation_store
import os
import secrets


class PullRequestServer(ThreadingHTTPServer):
    def __init__(self, gateway, token, port=8784, host="127.0.0.1"):
        if host != "127.0.0.1" or not isinstance(token, str) or len(token) < 32:
            raise ValueError("private_pr_service_required")

        class Handler(BaseHTTPRequestHandler):
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
                    self.headers.get("Authorization", ""), "Bearer " + token
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
                    if self.path == "/v1/github-prs/discover" and set(body) == {
                        "repository_url",
                        "labels",
                        "state",
                    }:
                        result = gateway.discover(**body)
                    elif self.path == "/v1/github-prs/execute" and set(body) in (
                        {"repository_url", "labels", "state", "pr_number", "operation"},
                        {
                            "repository_url",
                            "labels",
                            "state",
                            "pr_number",
                            "operation",
                            "expected",
                        },
                    ):
                        executing_write = bool(body["operation"])
                        result = gateway.execute(**body)
                    elif self.path == "/v1/github-prs/prepare-feedback" and set(
                        body
                    ) == {
                        "repository_url",
                        "labels",
                        "state",
                        "pr_number",
                        "expected",
                    }:
                        result = gateway.prepare_feedback(**body)
                    elif self.path == "/v1/github-prs/apply-feedback" and set(body) == {
                        "ticket",
                        "operation",
                    }:
                        executing_write = True
                        result = gateway.apply_feedback(**body)
                    else:
                        raise ValueError("invalid_request")
                    self.reply(200, result)
                except Exception as error:
                    category = (
                        str(error)
                        if type(error) is ValueError
                        and str(error) in _pull_requests_contract.ERROR_CODES
                        else "github_pr_unavailable"
                    )
                    if isinstance(
                        error, _mediation_errors.KnownRejected
                    ) and error.code in {
                        "github_http_401",
                        "github_http_403",
                        "github_http_404",
                        "github_http_410",
                    }:
                        category = error.code
                    if (
                        executing_write
                        and category not in _pull_requests_contract.PRE_DISPATCH_ERRORS
                    ):
                        self.reply(503, {"error_category": "pr_write_unknown"})
                    else:
                        self.reply(400, {"error_category": category})

        super().__init__((host, port), Handler)
