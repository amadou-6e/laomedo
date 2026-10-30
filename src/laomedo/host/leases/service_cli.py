"""Independent lease service for exact runner containers and scoped write grants.

The operator starts this service separately from the runner. The runner never
spawns it, so a whole-process-tree termination of the runner cannot reach it.
Runners register exact container leases in the service's private state
directory and refresh a heartbeat file. On a stale heartbeat the service first
revokes every write grant bound to that lease, then stops only the labelled
container recorded in the lease, and writes a timed, durable result.

The grant endpoint is a synthetic external-write target: it accepts a write
only while the bearer grant is active. It models the revocation boundary a
real push-credential broker must provide; it is not a GitHub credential."""

from __future__ import annotations

from pathlib import Path
import argparse
from laomedo.host.mediation.store import MediationStore


def main() -> None:
    from laomedo.host.leases.service import LeaseService

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="run the independent lease service")
    serve.add_argument("--state", type=Path, required=True)
    serve.add_argument("--port", type=int, default=0)
    serve.add_argument("--mediator-store", type=Path)
    serve.add_argument("--authority-store", type=Path)
    serve.add_argument("--repository")
    serve.add_argument("--connection-id")
    serve.add_argument("--connection-generation", type=int)
    args = parser.parse_args()
    selected = (
        args.mediator_store,
        args.authority_store,
        args.repository,
        args.connection_id,
        args.connection_generation,
    )
    if any(value is not None for value in selected):
        if any(value is None for value in selected):
            parser.error("mediated mode requires all store and connection options")
        from laomedo.host.mediation.authority import RunGrantAuthority

        def matches(connection_id, generation, repository, reviewed_by):
            return bool(reviewed_by) and (connection_id, generation, repository) == (
                args.connection_id,
                args.connection_generation,
                args.repository,
            )

        authority = RunGrantAuthority(
            args.authority_store, connection_authorizer=matches
        )
        mediator = MediationStore(
            args.mediator_store,
            connection_is_current=lambda cid, gen, repo: matches(
                cid, gen, repo, "lease-service"
            ),
        )
        service = LeaseService(
            args.state,
            port=args.port,
            mediator=mediator,
            mediation_authority=authority.authorize_lease,
        )
    else:
        service = LeaseService(args.state, port=args.port)
    service.serve()


if __name__ == "__main__":
    main()
