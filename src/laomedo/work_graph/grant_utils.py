"""grant utils helpers."""

from __future__ import annotations

from pathlib import Path
import csv
import laomedo.work_graph.runs.errors as _workflow_errors
import os
import re
import subprocess


def _private_path(path):
    target = Path(path).expanduser()
    if not target.is_absolute() or target.is_symlink():
        raise _workflow_errors.LaunchError("grant_store_path_invalid")
    resolved = target.resolve()
    if any(
        (parent / ".git").exists()
        for parent in (resolved.parent, *resolved.parent.parents)
    ):
        raise _workflow_errors.LaunchError("grant_store_inside_git")
    return resolved


def _host_principal():
    if os.name != "nt":
        return "uid:" + str(os.getuid())
    try:
        result = subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
        )
        rows = list(csv.reader(result.stdout.splitlines()))
        sid = rows[0][-1] if result.returncode == 0 and len(rows) == 1 else ""
    except (OSError, subprocess.TimeoutExpired, IndexError):
        sid = ""
    if not re.fullmatch(r"S-\d+(?:-\d+)+", sid):
        raise _workflow_errors.LaunchError("host_operator_identity_unavailable")
    return "sid:" + sid
