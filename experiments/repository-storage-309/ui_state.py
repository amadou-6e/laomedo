"""Reversible error states only in the named, app-owned storage validation clone."""

import argparse
import json
import os
from pathlib import Path

from acceptance_shell import StorageAcceptance


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "operation", choices=("conflict", "restore", "offline", "online")
    )
    arguments = parser.parse_args()
    acceptance = StorageAcceptance()
    acceptance.login()
    state = acceptance.request("/api/v1/laomedo/assistant/storage")
    repository = next(
        r for r in state["repositories"] if r["name"] == "Repository storage validation"
    )
    checkout = Path(repository["path"]).resolve()
    private = (
        Path(os.environ["LOCALAPPDATA"])
        / "Laomedo/acceptance/assistant-saved-293-01a1ba85"
    )
    expected = (private / "project-storage/checkouts").resolve()
    if not checkout.is_relative_to(expected) or checkout.parent.parent != expected:
        raise RuntimeError("wrong_acceptance_checkout")
    graph = checkout / "graphs/validation.json"
    backup = private / "storage-309-ui-original.json"
    git = checkout / ".git"
    offline = checkout / ".git-storage-309-validation-offline"
    if arguments.operation == "conflict":
        if backup.exists():
            raise RuntimeError("restore_prior_ui_probe_first")
        content = graph.read_bytes()
        json.loads(content)
        backup.write_bytes(content)
        graph.write_bytes(content + b"\n")
    elif arguments.operation == "restore":
        if backup.exists():
            graph.write_bytes(backup.read_bytes())
            backup.unlink()
    elif arguments.operation == "offline":
        if not git.is_dir() or offline.exists():
            raise RuntimeError("wrong_git_fixture_state")
        git.rename(offline)
    elif arguments.operation == "online":
        if offline.is_dir() and not git.exists():
            offline.rename(git)
    print(
        json.dumps({"operation": arguments.operation, "validation_fixture_only": True})
    )


if __name__ == "__main__":
    main()
