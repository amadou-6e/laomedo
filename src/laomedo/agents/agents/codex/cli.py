"""Implementation owned by agents / runtime / cli."""

from __future__ import annotations
from laomedo.agents.agents.codex.agent import CodexAgent

from pathlib import Path
import argparse
import json
from laomedo.host.runner.http.server import RunnerServer
from laomedo.host.mediation.authority import RunGrantAuthority


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--skill-store", type=Path, required=True)
    parser.add_argument("--source-workspace", type=Path, required=True)
    parser.add_argument(
        "--git-workspace",
        action="store_true",
        help="Opt-in isolated Git checkout; mediated push remains disabled",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument(
        "--image-id",
        help="Operator-approved SHA256 ID of a locally rebuilt non-Git image; the fixed version tag must match it",
    )
    parser.add_argument(
        "--lease-service",
        type=Path,
        help="State directory of an independently started lease service",
    )
    parser.add_argument(
        "--github-authority-store",
        type=Path,
        help="Trusted run-approval database outside the checkout",
    )
    parser.add_argument(
        "--mediator-state",
        type=Path,
        help="Private host mediator state; only its port is passed to Docker",
    )
    parser.add_argument(
        "--split-executor",
        action="store_true",
        help="Credential-free experimental split controller/executor",
    )
    parser.add_argument(
        "--auth-store",
        type=Path,
        help="Private app-owned ChatGPT OAuth store; requires --split-executor",
    )
    parser.add_argument(
        "--artifact-source", action="append", default=[], metavar="PROVIDER=STATE"
    )
    args = parser.parse_args()
    if (args.github_authority_store is None) != (args.mediator_state is None):
        parser.error("GitHub authority and mediator state must be configured together")
    authority = (
        RunGrantAuthority(args.github_authority_store)
        if args.github_authority_store
        else None
    )
    runner = CodexAgent(
        args.state,
        args.skill_store,
        args.source_workspace,
        git_workspace=args.git_workspace,
        lease_service=args.lease_service,
        github_authority=authority,
        mediator_state=args.mediator_state,
        split_executor=args.split_executor,
        auth_store=args.auth_store,
        image_id=args.image_id,
        artifact_sources=dict(item.split("=", 1) for item in args.artifact_source),
    )
    if args.preflight:
        print(json.dumps(runner.preflight(), indent=2))
        return
    RunnerServer(runner, port=args.port).serve_forever()


if __name__ == "__main__":
    main()
