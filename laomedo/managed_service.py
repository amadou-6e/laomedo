"""Bounded configuration-file entry point for independent host tasks.

This launcher reads paths and non-secret settings, not credential values.
The host service retains custody of its explicitly selected token file.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


_OPTIONS = {
    "host-services": {
        "state", "repository", "checkout", "baseline", "agent_mount",
        "runner_state", "private_stage", "connection_id",
        "connection_generation", "token_file", "token_key",
    },
    "bundle-verifier": {
        "runner_state", "private_root", "agent_mount", "baseline_bundle",
        "baseline_sha256",
    },
}


def configuration_arguments(service: str, path: Path) -> list[str]:
    """Fail closed on unexpected fields; never embed actual tokens in argv."""
    if service not in _OPTIONS or path.is_symlink() or not path.is_file():
        raise ValueError("managed_configuration_invalid")
    if path.stat().st_size > 16384:
        raise ValueError("managed_configuration_too_large")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) - _OPTIONS[service]:
        raise ValueError("managed_configuration_fields_invalid")
    arguments = []
    for key, item in value.items():
        if (not isinstance(item, (str, int)) or isinstance(item, bool) or
                not str(item) or any(c in str(item) for c in "\r\n\0")):
            raise ValueError("managed_configuration_value_invalid")
        arguments.extend(("--" + key.replace("_", "-"), str(item)))
    return arguments


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", required=True, choices=tuple(_OPTIONS))
    parser.add_argument("--configuration", required=True, type=Path)
    args = parser.parse_args()
    argv = configuration_arguments(args.service, args.configuration)
    # Run in the Scheduler-owned process, not as a runner child. Argparse in
    # the concrete service still checks required fields before any startup.
    if args.service == "host-services":
        from .host_services import main as start
    else:
        from .bundle_verifier import main as start
    sys.argv = [sys.argv[0], *argv]
    start()


if __name__ == "__main__":
    main()
