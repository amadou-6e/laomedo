"""One-time local handoff into a persistent private Codex profile.

This copies only the current file-backed ChatGPT auth, never settings, skills,
sessions, or plugins. The private copy must persist and be reused across tests.
Run only for the explicitly authorized single-user feasibility experiment.
"""

import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _shared import inside_git_tree


def provision(source: Path, state: Path) -> dict:
    if not state.is_dir() or state.is_symlink() or inside_git_tree(state):
        raise ValueError("private state must be an existing directory outside git")
    if not source.is_file() or source.is_symlink():
        raise FileNotFoundError("file-backed personal Codex auth unavailable")
    codex_home = state / "codex-home"
    if codex_home.is_symlink():
        raise ValueError("private Codex home cannot be a symlink")
    codex_home.mkdir(exist_ok=True)
    destination = codex_home / "auth.json"
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("private auth already exists; reuse it, do not copy again")
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as private:
            with source.open("rb") as original:
                while chunk := original.read(1024 * 1024):
                    private.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return {"provisioned": True, "mode": "chatgpt_handoff",
            "private_copy_reused_across_tests": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = provision(Path.home() / ".codex" / "auth.json",
                           args.state_dir.resolve(strict=True))
    except (OSError, ValueError) as exc:
        result = {"provisioned": False, "reason": type(exc).__name__,
                  "detail": str(exc)}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
