"""Implementation owned by host / mediation / cli."""

from __future__ import annotations

from pathlib import Path
import argparse
import json
from laomedo.github.transport.git.transport import GitHubGitTransport
from laomedo.github.transport.git.transport import GitHubMediatedTransport
from laomedo.github.transport.rest.transport import GitHubRestTransport
from laomedo.host.credentials.token.connection import HostTokenConnection
from laomedo.host.mediation.store import MediationStore
from laomedo.host.publication.verified.utils import classify_verified_workflow
from laomedo.host.publication.verified.utils import make_grant_bundle_freezer
from laomedo.host.publication.verified.utils import make_grant_stage_resolver
import os
import time


def main() -> None:
    from laomedo.host.mediation.service import JournaledTransport
    from laomedo.host.mediation.service import MediationHTTPService

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state",
        type=Path,
        required=True,
        help="private host-only state directory, never an agent mount",
    )
    parser.add_argument("--repository", required=True)
    parser.add_argument(
        "--checkout",
        type=Path,
        required=True,
        help="trusted host checkout containing the exact commit",
    )
    parser.add_argument(
        "--baseline",
        required=True,
        help="pinned baseline SHA for workflow-file classification",
    )
    parser.add_argument(
        "--agent-mount",
        type=Path,
        required=True,
        help="source tree mounted or copied into the agent",
    )
    parser.add_argument("--runner-state", type=Path)
    parser.add_argument("--private-stage", type=Path)
    parser.add_argument("--connection-id", required=True)
    parser.add_argument("--connection-generation", type=int, required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--token-key", default="GH")
    args = parser.parse_args()
    if (args.runner_state is None) != (args.private_stage is None):
        parser.error("both --runner-state and --private-stage are required together")
    state = args.state.resolve()
    state.mkdir(parents=True, exist_ok=True)
    connection = HostTokenConnection(
        connection_id=args.connection_id,
        generation=args.connection_generation,
        repository=args.repository,
        token_file=args.token_file,
        key=args.token_key,
        forbidden_mount=args.agent_mount,
    )
    resolver = (
        make_grant_stage_resolver(
            args.runner_state, args.private_stage, args.agent_mount
        )
        if args.runner_state is not None
        else None
    )
    freezer = (
        make_grant_bundle_freezer(
            args.runner_state,
            args.private_stage,
            args.agent_mount,
            confirmed_stage_authorizer=lambda grant, snapshot: store.confirmed_stage(
                grant, snapshot
            ),
        )
        if args.runner_state is not None
        else None
    )
    git_transport = GitHubGitTransport(
        args.repository,
        args.checkout,
        args.baseline,
        connection.token,
        require_verified_stage=True,
    )
    rest_transport = GitHubRestTransport(
        args.repository, connection.token
    )
    store = MediationStore(
        state / "mediator.sqlite",
        verified_stage_resolver=resolver,
        stage_freezer=freezer,
        verified_workflow_classifier=(
            classify_verified_workflow if resolver is not None else None
        ),
        connection_is_current=connection.current,
    )
    transport = GitHubMediatedTransport(git_transport, rest_transport)
    service = MediationHTTPService(
        store,
        JournaledTransport(
            transport,
            state / "provider-attempts.jsonl",
            state / "push-diagnostics.jsonl",
        ),
    )
    # This file contains no token, only the instance/port required by a
    # trusted controller. It is never copied into a run workspace.
    status = state / "mediator.json"
    pending = status.with_suffix(".pending")
    pending.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "port": service.port,
                "instance": service.instance,
                "started_at": time.time(),
                "connection_id": args.connection_id,
                "generation": args.connection_generation,
                "repository": args.repository,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    os.replace(pending, status)
    try:
        service.serve()
    finally:
        service.close()


if __name__ == "__main__":
    main()
