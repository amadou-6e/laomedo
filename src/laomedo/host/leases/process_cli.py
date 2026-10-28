"""Implementation owned by host / leases / process_cli."""

from __future__ import annotations

from pathlib import Path
import argparse
import laomedo.host.leases.utils as _leases_utils


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("record", type=Path)
    parser.add_argument("name")
    parser.add_argument("run_id")
    parser.add_argument("token")
    parser.add_argument("ready", type=Path)
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    raise SystemExit(
        _leases_utils.supervise(
            args.record, args.name, args.run_id, args.token, args.ready, args.result
        )
    )


if __name__ == "__main__":
    main()
