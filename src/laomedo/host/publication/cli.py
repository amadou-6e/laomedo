"""Implementation owned by host / publication / cli."""

from __future__ import annotations

from pathlib import Path
import argparse
import json
import os
import secrets
import threading
import time


def main():
    # Explicitly refuse ambient provider overrides rather than falling back.
    from laomedo.host.publication.verifier import BundleVerifier

    if any(
        key in os.environ
        for key in ("GH_TOKEN", "GITHUB_TOKEN", "GH_LAOMEDO", "GH", "GIT_ASKPASS")
    ):
        raise ValueError("verifier_credential_environment_denied")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-state", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--agent-mount", type=Path, required=True)
    parser.add_argument("--baseline-bundle", type=Path, required=True)
    parser.add_argument("--baseline-sha256", required=True)
    args = parser.parse_args()
    worker = BundleVerifier(**vars(args))
    try:
        worker.serve(threading.Event())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
