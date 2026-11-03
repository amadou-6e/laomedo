"""Command-line entry point for laomedo.github.pull_requests.server."""

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

from laomedo.github.pull_requests.server import PullRequestServer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument(
        "--feedback-bindings",
        type=Path,
        help="Host-only JSON mapping repository#PR to existing scoped grant reference",
    )
    credentials = parser.add_mutually_exclusive_group(required=True)
    credentials.add_argument("--github-token-env")
    credentials.add_argument("--github-token-file", type=Path)
    parser.add_argument("--github-token-key", default="GH_LAOMEDO")
    parser.add_argument("--connection-id", default="github-pr-local")
    parser.add_argument("--connection-generation", type=int, default=1)
    parser.add_argument("--forbidden-agent-mount", type=Path)
    parser.add_argument("--api-token-file", type=Path, required=True)
    parser.add_argument("--mediation-store", type=Path, required=True)
    parser.add_argument("--grant-bindings", type=Path)
    parser.add_argument("--port", type=int, default=8784)
    args = parser.parse_args()
    args.repository = args.repository.lower()
    if args.github_token_file:
        connection = _token_connection.HostTokenConnection(
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

    transport = _rest_transport.GitHubRestTransport(args.repository, credential)
    mediation = _mediation_store.MediationStore(
        args.mediation_store, connection_is_current=current
    )

    def grant(ref):
        if args.grant_bindings is None:
            raise ValueError("pr_grant_unavailable")
        bindings = json.loads(args.grant_bindings.read_text(encoding="utf-8"))
        return bindings[ref]

    feedback_grants = (
        json.loads(args.feedback_bindings.read_text(encoding="utf-8"))
        if args.feedback_bindings
        else {}
    )
    gateway = _pull_requests_gateway.GitHubPRGateway(
        {args.repository: transport}, mediation, grant, feedback_grants=feedback_grants
    )
    PullRequestServer(
        gateway, args.api_token_file.read_text(encoding="utf-8").strip(), port=args.port
    ).serve_forever()


if __name__ == "__main__":
    main()
