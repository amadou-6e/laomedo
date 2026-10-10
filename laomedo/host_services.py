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
from .verified_git_stage import (make_grant_stage_resolver,
                                 make_grant_bundle_freezer,
                                 classify_verified_workflow)


def build_services(*, state: Path, repository: str, checkout: Path,
                   baseline: str, agent_mount: Path, connection_id: str,
                   connection_generation: int, token_file: Path,
                   token_key: str = "GH", runner_state: Path | None = None,
                   private_stage: Path | None = None) -> tuple[LeaseService, MediationHTTPService]:
    state = state.expanduser().resolve()
    state.mkdir(parents=True, exist_ok=True)
    (state / "mediator").mkdir(exist_ok=True)
    connection = HostTokenConnection(
        connection_id=connection_id, generation=connection_generation,
        repository=repository, token_file=token_file, key=token_key,
        forbidden_mount=agent_mount)
    if (runner_state is None) != (private_stage is None):
        raise ValueError("verified_stage_roots_incomplete")
    resolver = (make_grant_stage_resolver(runner_state, private_stage,
                                         agent_mount)
                if runner_state is not None else None)
    freezer = (make_grant_bundle_freezer(runner_state, private_stage,
                                        agent_mount, confirmed_stage_authorizer=lambda grant, snapshot:
                                            store.confirmed_stage(grant, snapshot))
               if runner_state is not None else None)
    git_transport = GitHubGitTransport(repository, checkout, baseline,
                                       connection.token,
                                       require_verified_stage=True)
    rest_transport = GitHubRestTransport(repository, connection.token)
    store = MediationStore(
        state / "mediator" / "mediator.sqlite",
        verified_stage_resolver=resolver,
        stage_freezer=freezer,
        verified_workflow_classifier=(classify_verified_workflow
                                      if resolver is not None else None),
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
        "module_root": str(Path(__file__).resolve().parent),
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
    parser.add_argument("--runner-state", type=Path)
    parser.add_argument("--private-stage", type=Path)
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
