"""Import/fetch snapshots, then inspect a filtered projection."""

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

from .github import fetch, import_pages
from .grants import LocalGrantAuthority
from .local_launch import launch_local_saved_flow
from .model import GraphSnapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("fetch", "import"):
        command = commands.add_parser(name)
        command.add_argument("--repo", required=True)
        command.add_argument("--output-dir", type=Path, required=True)
        if name == "import":
            command.add_argument("--file", type=Path, required=True,
                                 help="JSON array of captured GraphQL response pages")
    inspect = commands.add_parser("inspect")
    inspect.add_argument("snapshot", type=Path)
    inspect.add_argument("--state", choices=("all", "open", "closed"), default="all")
    inspect.add_argument("--label", action="append", default=[])
    issue = commands.add_parser("issue-grant")
    issue.add_argument("snapshot", type=Path)
    issue.add_argument("--work-key", required=True)
    issue.add_argument("--grant-store", required=True, type=Path)
    issue.add_argument("--timeout-seconds", required=True, type=int)
    issue.add_argument("--max-turns", required=True, type=int)
    issue.add_argument("--expires-in-minutes", type=int, default=10)
    launch = commands.add_parser("launch")
    launch.add_argument("snapshot", type=Path)
    launch.add_argument("--work-key", required=True)
    launch.add_argument("--flow-id", required=True)
    launch.add_argument("--langflow-base", required=True)
    launch.add_argument("--grant-store", required=True, type=Path)
    launch.add_argument("--grant-ref", required=True)
    launch.add_argument("--run-store", required=True, type=Path)
    launch.add_argument("--task", required=True)
    launch.add_argument("--choice", choices=("pinned", "refreshed"))
    args = parser.parse_args(argv)
    try:
        if args.command == "launch":
            print(json.dumps(launch_local_saved_flow(
                snapshot_path=args.snapshot, work_key=args.work_key,
                flow_id=args.flow_id, langflow_base=args.langflow_base,
                grant_store=args.grant_store, grant_ref=args.grant_ref,
                run_store=args.run_store, task=args.task, choice=args.choice)))
        elif args.command == "issue-grant":
            snapshot = GraphSnapshot.from_dict(json.loads(args.snapshot.read_text(encoding="utf-8")))
            if not snapshot.source_complete or args.work_key not in {item.key for item in snapshot.items}:
                raise ValueError("A complete snapshot containing the selected work is required")
            if not 1 <= args.expires_in_minutes <= 60:
                raise ValueError("Grant expiry must be within 1 to 60 minutes")
            if not sys.stdin.isatty():
                raise ValueError("Interactive host terminal required for grant confirmation")
            confirmation = input(f"Type {args.work_key} to confirm a local zero-turn grant: ")
            if confirmation != args.work_key:
                raise ValueError("Operator confirmation did not match selected work")
            authority = LocalGrantAuthority(args.grant_store)
            expiry = (datetime.now(timezone.utc) + timedelta(
                minutes=args.expires_in_minutes)).isoformat()
            ref = authority.issue(work_key=args.work_key,
                graph_snapshot_id=snapshot.snapshot_id,
                expires_at=expiry,
                timeout_seconds=args.timeout_seconds, max_turns=args.max_turns)
            print(json.dumps({"grant_ref": ref, "work_key": args.work_key,
                "graph_snapshot_id": snapshot.snapshot_id,
                "expires_at": expiry, "timeout_seconds": args.timeout_seconds,
                "max_turns": args.max_turns}))
        elif args.command == "inspect":
            snapshot = GraphSnapshot.from_dict(json.loads(args.snapshot.read_text(encoding="utf-8")))
            print(json.dumps(snapshot.project(args.state, tuple(args.label)), indent=2))
        else:
            snapshot = fetch(args.repo) if args.command == "fetch" else import_pages(
                args.repo, json.loads(args.file.read_text(encoding="utf-8")))
            path = snapshot.save(args.output_dir)
            print(json.dumps({"snapshot_id": snapshot.snapshot_id, "path": str(path),
                              "source_complete": snapshot.source_complete,
                              "items": len(snapshot.items),
                              "dependencies": len(snapshot.dependencies)}))
        return 0
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
        parser.exit(2, f"Work Graph: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
