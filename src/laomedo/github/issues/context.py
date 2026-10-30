"""Read-only selected-issue context for the EXP-02 integration probe.

Timeline cross-references are candidates, not an exhaustive PR search and never
authorization to update a PR. All GitHub calls are reads through the existing
``gh`` login; no credentials or raw command errors enter the returned record."""

from __future__ import annotations

import json
from laomedo.github.issues.errors import IssueContextError
from laomedo.github.issues.context_reader import fetch_context


def main() -> int:
    """Print the existing read-only context/error JSON using unchanged CLI arguments."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", help="owner/repo")
    parser.add_argument("issue", type=int)
    parser.add_argument("--target-pr", type=int, default=None)
    args = parser.parse_args()
    try:
        result = fetch_context(
            args.repository, args.issue, supplied_target_pr=args.target_pr
        )
    except IssueContextError as error:
        print(json.dumps({"error": error.code}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
