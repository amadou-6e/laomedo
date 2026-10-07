"""CLI-shaped stand-in for an agent invoking the EXP-100 broker."""

import argparse
import json
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--grant", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--effect-id")
    parser.add_argument("operation")
    parser.add_argument("--payload", default="{}")
    args = parser.parse_args()
    request = {"grant": args.grant, "repo": args.repo, "operation": args.operation,
               "effect_id": args.effect_id, "payload": json.loads(args.payload)}
    encoded = json.dumps(request).encode()
    try:
        with urlopen(Request(args.url + "/command", encoded, {"Content-Type": "application/json"}), timeout=20) as response:
            status, result = response.status, json.load(response)
    except HTTPError as error:
        status, result = error.code, json.load(error)
    print(json.dumps({"http_status": status, **result}, sort_keys=True))
    return 0 if status < 300 else 1


if __name__ == "__main__":
    sys.exit(main())
