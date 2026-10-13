"""Loopback backend for live issue reads and existing scoped operation grants."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import json
import os
from pathlib import Path
import secrets
from .github_issue_gateway import GitHubIssueGateway
from .github_mediation import MediationStore, KnownRejected
from .github_rest_transport import GitHubRestTransport
from .host_token_connection import HostTokenConnection


from .github_issue_contract import ERROR_CODES

SAFE_ERRORS = ERROR_CODES


def server(gateway, token, port=8783, host="127.0.0.1"):
    if host != "127.0.0.1" or not isinstance(token, str) or len(token) < 32:
        raise ValueError("private_issue_service_required")
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
            if not secrets.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                self.reply(401, {"error_category": "unauthorized"}); return
            try:
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("invalid_request")
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 1024 * 1024:
                    raise ValueError("invalid_request")
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError("invalid_request")
                if self.path == "/v1/github-issues/discover" and set(body) == {"repository_url", "labels", "state"}:
                    result = gateway.discover(**body)
                elif self.path == "/v1/github-issues/execute" and set(body) == {"repository_url", "labels", "state", "issue_number", "operation"}:
                    result = gateway.execute(**body)
                else:
                    raise ValueError("invalid_request")
                self.reply(200, result)
            except Exception as error:
                category = str(error) if type(error) is ValueError and str(error) in SAFE_ERRORS else "github_issue_unavailable"
                if isinstance(error, KnownRejected) and error.code in {"github_http_401", "github_http_403", "github_http_404", "github_http_410"}:
                    category = error.code
                self.reply(400, {"error_category": category})
    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    credentials = parser.add_mutually_exclusive_group(required=True)
    credentials.add_argument("--github-token-env")
    credentials.add_argument("--github-token-file", type=Path)
    parser.add_argument("--github-token-key", default="GH_LAOMEDO")
    parser.add_argument("--connection-id", default="github-issue-local")
    parser.add_argument("--connection-generation", type=int, default=1)
    parser.add_argument("--forbidden-agent-mount", type=Path)
    parser.add_argument("--api-token-file", type=Path, required=True)
    parser.add_argument("--mediation-store", type=Path, required=True)
    parser.add_argument("--grant-bindings", type=Path)
    parser.add_argument("--port", type=int, default=8783)
    args = parser.parse_args()
    args.repository = args.repository.lower()
    if args.github_token_file:
        connection = HostTokenConnection(connection_id=args.connection_id,
            generation=args.connection_generation, repository=args.repository,
            token_file=args.github_token_file, key=args.github_token_key,
            forbidden_mount=args.forbidden_agent_mount)
        current = connection.current
        def credential(connection_id=None, connection_generation=None):
            return connection.token(connection_id or args.connection_id,
                                    args.connection_generation if connection_generation is None else connection_generation)
    else:
        # Explicit configured connection only; changes invalidate its generation.
        initial = os.environ.get(args.github_token_env)
        if not initial:
            raise ValueError("connection_unavailable")
        def current(connection_id, generation, repository):
            return ((connection_id, generation, repository) ==
                    (args.connection_id, args.connection_generation, args.repository) and
                    secrets.compare_digest(os.environ.get(args.github_token_env, ""), initial))
        def credential(connection_id=None, connection_generation=None):
            if not current(connection_id or args.connection_id,
                           args.connection_generation if connection_generation is None else connection_generation,
                           args.repository):
                raise ValueError("connection_unavailable")
            return initial
    transport = GitHubRestTransport(args.repository, credential)
    mediation = MediationStore(args.mediation_store, connection_is_current=current)
    def grant(ref):
        if args.grant_bindings is None:
            raise ValueError("issue_grant_unavailable")
        bindings = json.loads(args.grant_bindings.read_text(encoding="utf-8"))
        return bindings[ref]
    gateway = GitHubIssueGateway({args.repository: transport}, mediation, grant)
    server(gateway, args.api_token_file.read_text(encoding="utf-8").strip(), port=args.port).serve_forever()


if __name__ == "__main__":
    main()
