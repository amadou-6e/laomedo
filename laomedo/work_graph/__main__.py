"""Import/fetch snapshots, then inspect a filtered projection."""

import argparse
import json
from pathlib import Path

from .github import fetch, import_pages
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
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
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
