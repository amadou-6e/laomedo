"""Command-line entry point for laomedo.github.interface.issues.server."""

from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from pathlib import Path
import argparse
import json
from laomedo.github.issues.gateway import GitHubIssueGateway
from laomedo.github.transport.rest.transport import GitHubRestTransport
from laomedo.host.credentials.token.connection import HostTokenConnection
from laomedo.host.mediation.store import MediationStore
import os
import secrets

from laomedo.github.interface.issues.server import IssueServer


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
        connection = HostTokenConnection(
            connection_id=args.connection_id,
            generation=args.connection_generation,
            repository=args.repository,
            token_file=args.github_token_file,
            key=args.github_token_key,
            forbidden_mount=args.forbidden_agent_mount,
        )
        current = connection.current

        def credential(connection_id=None, connection_generation=None):
            return connection.token(
                connection_id or args.connection_id,
                (
                    args.connection_generation
                    if connection_generation is None
                    else connection_generation
                ),
            )

    else:
        # Explicit configured connection only; changes invalidate its generation.
        initial = os.environ.get(args.github_token_env)
        if not initial:
            raise ValueError("connection_unavailable")

        def current(connection_id, generation, repository):
            return (connection_id, generation, repository) == (
                args.connection_id,
                args.connection_generation,
                args.repository,
            ) and secrets.compare_digest(
                os.environ.get(args.github_token_env, ""), initial
            )

        def credential(connection_id=None, connection_generation=None):
            if not current(
                connection_id or args.connection_id,
                (
                    args.connection_generation
                    if connection_generation is None
                    else connection_generation
                ),
                args.repository,
            ):
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
    IssueServer(
        gateway, args.api_token_file.read_text(encoding="utf-8").strip(), port=args.port
    ).serve_forever()


if __name__ == "__main__":
    main()
