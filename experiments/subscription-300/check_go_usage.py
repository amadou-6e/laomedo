"""Point-in-time zero-inference feasibility check; never a production dependency."""

import argparse
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener
from uuid import UUID

from laomedo.agents.connections.models import ConnectionIndex
from laomedo.host.http import NoRedirect


def main():
    """Use only the explicitly selected saved Go key at its official usage URL."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--connection", required=True, type=UUID)
    options = parser.parse_args()
    root = options.root.resolve(strict=True)
    matches = []
    for index in root.glob("*/connections.json"):
        for row in ConnectionIndex.model_validate_json(index.read_bytes()).connections:
            if row.connection_id == options.connection:
                matches.append((index, row))
    if len(matches) != 1:
        raise SystemExit("Exact saved connection not found")
    index, row = matches[0]
    if (
        row.provider != "opencode"
        or row.client_id != "opencode-go"
        or row.lifecycle != "connected"
    ):
        raise SystemExit("Selected Go connection is not admitted")
    revision = (index.parent / str(row.credential_id)).resolve(strict=True)
    if not revision.is_relative_to(root):
        raise SystemExit("Credential revision escaped the runtime")
    auth = json.loads((revision / "auth.json").read_bytes())["opencode-go"]
    key = auth.get("key")
    if (
        auth.get("type") != "api"
        or not isinstance(key, str)
        or hashlib.sha256(key.encode()).hexdigest() != row.subject_hash
    ):
        raise SystemExit("Credential binding changed")
    request = Request(
        "https://opencode.ai/inference/go/v1/usage",
        headers={"Authorization": "Bearer " + key, "Accept": "application/json"},
        method="GET",
    )
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(
            request, timeout=30
        ) as response:
            data = response.read(65537)
            status = response.status
    except HTTPError as error:
        kind = "unclassified"
        try:
            body = json.loads(error.read(65536))
            candidate = body.get("error", {}).get("type")
            if candidate in {
                "EntitlementError",
                "AuthenticationError",
                "PermissionError",
                "RateLimitError",
            }:
                kind = candidate
        except (ValueError, AttributeError, TypeError):
            pass
        print(
            json.dumps(
                {"http_status": error.code, "error_type": kind, "submitted_turns": 0}
            )
        )
        return
    except URLError:
        raise SystemExit("Official usage endpoint unavailable") from None
    current = ConnectionIndex.model_validate_json(index.read_bytes()).connections
    if row not in current or len(data) > 65536:
        raise SystemExit("Saved binding changed or response exceeded bound")
    usage = json.loads(data).get("usage")
    if not isinstance(usage, dict):
        raise SystemExit("No supported usage object returned")
    print(
        json.dumps(
            {
                "http_status": status,
                "submitted_turns": 0,
                "windows": {
                    name: {
                        field: usage[name].get(field)
                        for field in ("status", "percent", "resetsAt")
                    }
                    for name in ("rolling", "weekly", "monthly")
                    if isinstance(usage.get(name), dict)
                },
            }
        )
    )


if __name__ == "__main__":
    main()
