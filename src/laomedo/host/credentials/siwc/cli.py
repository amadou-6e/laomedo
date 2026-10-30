"""Implementation owned by host / credentials / siwc / cli."""

from __future__ import annotations

from pathlib import Path
import json
from laomedo.host.credentials.siwc.browser import browser_connect
from laomedo.host.credentials.siwc.errors import AuthError


def main() -> None:
    from laomedo.host.credentials.siwc.connection import ChatGPTConnection
    import argparse

    parser = argparse.ArgumentParser(description="Laomedo local ChatGPT connection")
    parser.add_argument("--store", type=Path, required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    connect = sub.add_parser("connect")
    connect.add_argument("--client-id")
    sub.add_parser("status")
    sub.add_parser("list")
    switch = sub.add_parser("switch")
    switch.add_argument("client_id")
    sub.add_parser("sign-out")
    args = parser.parse_args()
    try:
        store = ChatGPTConnection(args.store)
        if args.action == "connect":
            result = browser_connect(store, client_id=args.client_id)
        elif args.action == "status":
            result = store.summary(store.active())
        elif args.action == "list":
            result = {
                "accounts": [
                    {"client_id": entry["client_id"], **store.summary(entry)}
                    for path in sorted(store.accounts.glob("*.json"))
                    if isinstance((entry := json.loads(path.read_text())), dict)
                ]
            }
        elif args.action == "switch":
            result = store.switch(args.client_id)
        else:
            result = store.sign_out()
        print(json.dumps(result, sort_keys=True))
    except AuthError as exc:
        print(json.dumps({"auth_outcome": "failed", "error_category": str(exc)}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
