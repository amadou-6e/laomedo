"""Local CLI functions; no network, subprocess execution or model invocation."""

import argparse
import json
from pathlib import Path
import sys
import sqlite3

from pydantic import BaseModel, ValidationError

from session_retro.errors import RetrospectiveError
from session_retro.index import SessionIndex
from session_retro.models import OperationFailure
from session_retro.reader import SessionReader
from session_retro.report import RetrospectiveReport
from session_retro.settings import Settings
from session_retro.settings import ERROR_MESSAGES


def main() -> int:
    """Execute one explicit local evidence command.

    Returns
    -------
    int
        Zero on success, one on a handled domain/filesystem/settings failure.

    Notes
    -----
    Parses process arguments and environment at invocation. Commands may read only
    the selected original and write admitted private artifacts. Bounded results go
    to stdout; safe descriptive failures go to stderr. No model/network invocation.
    """
    parser = argparse.ArgumentParser(
        description="Private bounded Codex evidence, not automatic incident judgments"
    )
    parser.add_argument(
        "--private-root",
        type=Path,
        help="Required private output root, or RETRO_PRIVATE_ROOT",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    inventory = commands.add_parser("inventory")
    inventory.add_argument("--source", type=Path, required=True)
    inventory.add_argument("--session-id", required=True)
    for name in ("index", "coverage", "search", "read", "verify", "report"):
        sub = commands.add_parser(name)
        sub.add_argument("--database", type=Path, required=True)
        if name == "index":
            sub.add_argument("--source", type=Path, required=True)
            sub.add_argument("--session-id", required=True)
            sub.add_argument("--extend", action="store_true")
            sub.add_argument("--stop-after", type=int)
            sub.add_argument(
                "--boundary",
                type=int,
                help="Pin an earlier captured byte boundary for reproducible rebuilds",
            )
        elif name == "search":
            sub.add_argument("query")
            sub.add_argument("--after", type=int, default=0)
            sub.add_argument("--kind")
        elif name == "read":
            sub.add_argument("--line", type=int, required=True)
            sub.add_argument("--start", type=int, default=0)
        elif name == "report":
            sub.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    index = None
    try:
        settings = Settings(
            **({"private_root": args.private_root} if args.private_root else {})
        )
        if args.command == "inventory":
            _emit(SessionReader(args.source, settings).snapshot(args.session_id))
            return 0
        if args.command == "index" and args.source.resolve() == args.database.resolve():
            raise RetrospectiveError("source_is_database")
        index = SessionIndex(args.database, settings, create=args.command == "index")
        if args.command == "index":
            if args.stop_after is not None and args.stop_after < 1:
                raise RetrospectiveError("invalid_stop_after")
            result = index.build(
                args.source,
                args.session_id,
                extend=args.extend,
                stop_after=args.stop_after,
                boundary=args.boundary,
            )
        elif args.command == "coverage":
            result = index.coverage()
        elif args.command == "search":
            result = index.search(args.query, after=args.after, kind=args.kind)
        elif args.command == "read":
            result = index.read(args.line, start=args.start)
        elif args.command == "verify":
            result = index.verify()
        else:
            result = RetrospectiveReport(index).write(args.directory)
        _emit(result)
        return 0
    except (RetrospectiveError, OSError, ValidationError, sqlite3.Error) as failure:
        code = (
            failure.code
            if isinstance(failure, RetrospectiveError)
            else "filesystem_or_settings_failed"
        )
        print(
            OperationFailure(
                code=code,
                message=ERROR_MESSAGES.get(
                    code, ERROR_MESSAGES["filesystem_or_settings_failed"]
                ),
            ).model_dump_json(),
            file=sys.stderr,
        )
        return 1
    finally:
        if index is not None:
            index.close()


def _emit(value) -> None:
    """Serialize bounded command results; private text is never automatically sent."""
    if isinstance(value, list):
        value = [
            item.model_dump(mode="json") if isinstance(item, BaseModel) else item
            for item in value
        ]
    elif isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    print(json.dumps(value, ensure_ascii=True, indent=2))
