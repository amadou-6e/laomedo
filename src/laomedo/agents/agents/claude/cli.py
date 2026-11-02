"""Implementation owned by agents / providers / claude / cli."""

from __future__ import annotations

from pathlib import Path
from laomedo.agents.agents.claude.settings import IMAGE
from laomedo.agents.agents.claude.settings import PROFILE
from laomedo.agents.errors import RunnerError
import threading


def main():
    from laomedo.agents.agents.claude.agent import ClaudeAgent
    import argparse
    from laomedo.host.runner.http.server import RunnerServer

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--skill-store", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--image", default=IMAGE)
    parser.add_argument("--profile-volume", default=PROFILE)
    parser.add_argument("--lease-service", type=Path, required=True)
    parser.add_argument("--turn-timeout", type=int, default=180)
    parser.add_argument("--port", type=int, default=8769)
    parser.add_argument("--github-authority-store", type=Path)
    parser.add_argument("--mediator-state", type=Path)
    parser.add_argument("--git-workspace", action="store_true")
    parser.add_argument(
        "--artifact-source", action="append", default=[], metavar="PROVIDER=STATE"
    )
    args = parser.parse_args()
    if (args.github_authority_store is None) != (args.mediator_state is None):
        parser.error("GitHub authority and mediator state must be configured together")
    from laomedo.host.mediation.authority import RunGrantAuthority

    authority = (
        RunGrantAuthority(args.github_authority_store)
        if args.github_authority_store
        else None
    )
    runner = ClaudeAgent(
        args.state,
        args.skill_store,
        args.source,
        image=args.image,
        profile_volume=args.profile_volume,
        lease_service=args.lease_service,
        turn_timeout=args.turn_timeout,
        github_authority=authority,
        mediator_state=args.mediator_state,
        git_workspace=args.git_workspace,
        artifact_sources=dict(item.split("=", 1) for item in args.artifact_source),
    )
    # Authentication and discovery belong to editor refresh or dispatch.
    # Completed-run Status and Activity remain available when login expires.
    server = RunnerServer(runner, port=args.port)

    def warm_catalog():
        try:
            runner.model_catalog()
        except RunnerError:
            pass  # Saved Status/Activity stay available; editor refresh reports recovery.

    threading.Thread(target=warm_catalog, daemon=True).start()
    server.serve_forever()


if __name__ == "__main__":
    main()
