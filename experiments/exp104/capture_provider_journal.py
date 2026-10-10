"""Copy the exact non-secret D2 provider journal bytes for review.

The mediation service writes only an allowlist of metadata. This capture
checks that shape and refuses a destination that already exists. The source
remains in private local state; no credential value or digest is recorded.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ALLOWED = {"at_wall", "at_monotonic", "repository", "operation", "branch", "commit"}
EXPECTED = ["git_push", "api_rest_read", "api_rest_read", "api_rest_read"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    source, target = args.source.resolve(), args.target.resolve()
    if target.exists() or not source.is_file() or not target.parent.is_dir():
        parser.error("source_and_fresh_target_required")
    data = source.read_bytes()
    lines = data.decode("utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    if (len(records) != 4 or [item.get("operation") for item in records] != EXPECTED or
            any(not isinstance(item, dict) or not set(item) <= ALLOWED or
                item.get("repository") != "ga84jog/laomedo-exp104-disposable-20261007"
                for item in records)):
        raise RuntimeError("provider_journal_shape_invalid")
    with target.open("xb") as output:
        output.write(data)
    print(json.dumps({"provider_attempts": len(records), "exact_byte_copy": True}))


if __name__ == "__main__":
    main()
