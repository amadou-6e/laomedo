"""Implementation owned by host / runner / utils."""

from __future__ import annotations

from laomedo._paths import import_root
import os


def service_environment(provider):
    allowed = {
        "PATH",
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "SYSTEMROOT",
        "WINDIR",
        "SYSTEMDRIVE",
        "COMSPEC",
        "PATHEXT",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "HOMEDRIVE",
        "HOMEPATH",
        "PROGRAMDATA",
        "USERNAME",
    }
    if provider in {"codex", "claude"}:
        allowed.update(
            {
                "DOCKER_HOST",
                "DOCKER_TLS_VERIFY",
                "DOCKER_CERT_PATH",
                "DOCKER_CONTEXT",
                "DOCKER_CONFIG",
            }
        )
    return {
        **{key: value for key, value in os.environ.items() if key.upper() in allowed},
        "PYTHONPATH": str(import_root()),
    }
