"""Host-only Git credential helper for a single mediated HTTPS operation.

The mediator passes the credential in this helper's process environment, not
in a URL, Git command line, repository config, or agent container. Never log
the helper's input or output.
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] != "get":
        return 0
    fields = {}
    for line in sys.stdin:
        if line == "\n":
            break
        key, _, value = line.rstrip("\r\n").partition("=")
        fields[key] = value
    token = os.environ.get("LAOMEDO_MEDIATED_GIT_TOKEN", "")
    if (fields.get("protocol") != "https" or
            fields.get("host") != "github.com" or
            not token or "\n" in token or "\r" in token):
        return 1
    sys.stdout.write("username=x-access-token\n")
    sys.stdout.write("password=" + token + "\n\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
