"""Run the credential mediator and lease supervisor outside the agent runner.

Start this foreground command under an independent host service manager. It
never runs inside the runner's process tree, and does not dispatch agents.
Restart invalidates existing lease scopes; it does not adopt or re-dispatch
their work. Production service-manager installation remains deployment work.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import threading
import time

from .github_git_transport import GitHubGitTransport, GitHubMediatedTransport
from .github_mediation import MediationStore
from .github_rest_transport import GitHubRestTransport
from .host_token_connection import HostTokenConnection
from .lease_service import LeaseService
from .mediation_authority import RunGrantAuthority
from .mediation_service import JournaledTransport, MediationHTTPService


def build_services(*, state: Path, repository: str, checkout: Path,
                   baseline: str, agent_mount: Path, connection_id: str,
                   connection_generation: int, token_file: Path,
                   token_key: str = "GH") -> tuple[LeaseService, MediationHTTPService]:
    state = state.expanduser().resolve()
    state.mkdir(parents=True, exist_ok=True)
    (state / "mediator").mkdir(exist_ok=True)
    connection = HostTokenConnection(
        connection_id=connection_id, generation=connection_generation,
        repository=repository, token_file=token_file, key=token_key,
        forbidden_mount=agent_mount)
    git_transport = GitHubGitTransport(repository, checkout, baseline,
                                       connection.token)
    rest_transport = GitHubRestTransport(repository, connection.token)
    store = MediationStore(
        state / "mediator" / "mediator.sqlite",
        workflow_change_classifier=git_transport.classify_workflow_diff,
        connection_is_current=connection.current)
    authority = RunGrantAuthority(state / "authority.sqlite",
                                  connection_authorizer=connection.authorize)
    lease = LeaseService(state / "lease", mediator=store,
                         mediation_authority=authority.authorize_lease)
    transport = JournaledTransport(
        GitHubMediatedTransport(git_transport, rest_transport),
        state / "mediator" / "provider-attempts.jsonl",
        state / "mediator" / "push-diagnostics.jsonl")
    mediator = MediationHTTPService(store, transport)
    return lease, mediator


def serve_services(lease: LeaseService, mediator: MediationHTTPService,
                   state: Path, *, repository: str, connection_id: str,
                   connection_generation: int) -> None:
    """Publish mediator identity, then keep both host services alive together."""
    mediator_state = state / "mediator"
    mediator_state.mkdir(parents=True, exist_ok=True)
    status = mediator_state / "mediator.json"
    pending = status.with_suffix(".pending")
    pending.write_text(json.dumps({
        "pid": os.getpid(), "port": mediator.port,
        "instance": mediator.instance, "started_at": time.time(),
        "connection_id": connection_id,
        "generation": connection_generation,
        "repository": repository}) + "\n", encoding="utf-8")
    os.replace(pending, status)
    thread = threading.Thread(target=mediator.serve, daemon=True,
                              name="laomedo-mediator")
    thread.start()
    try:
        lease.serve()
    finally:
        mediator.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--checkout", required=True, type=Path)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--agent-mount", required=True, type=Path)
    parser.add_argument("--connection-id", required=True)
    parser.add_argument("--connection-generation", required=True, type=int)
    parser.add_argument("--token-file", required=True, type=Path)
    parser.add_argument("--token-key", default="GH")
    args = parser.parse_args()
    lease, mediator = build_services(**vars(args))
    serve_services(lease, mediator, args.state.resolve(),
                   repository=args.repository, connection_id=args.connection_id,
                   connection_generation=args.connection_generation)


if __name__ == "__main__":
    main()
