"""Read-only, bounded checks of the host-owned Docker installation/context."""

import re
import shutil
import subprocess

ERROR_CODES = frozenset(
    {
        "runner_docker_not_installed",
        "runner_docker_unavailable",
        "runner_docker_check_unconfirmed",
    }
)


def check_docker(environment):
    path = next((v for k, v in environment.items() if k.upper() == "PATH"), None)
    executable = shutil.which("docker", path=path)
    if executable is None:
        # Absence from PATH is not proof that the user uninstalled Docker.
        return "runner_docker_not_installed"
    try:
        result = subprocess.run(
            [executable, "info", "--format", "{{.ServerVersion}}"],
            env=environment,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except FileNotFoundError:
        return "runner_docker_not_installed"
    except (OSError, subprocess.SubprocessError):
        return "runner_docker_check_unconfirmed"
    if result.returncode == 0:
        return (
            None
            if re.fullmatch(
                r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9_.+-]+)?", result.stdout.strip()
            )
            else "runner_docker_check_unconfirmed"
        )
    error = result.stderr[:8192].lower()
    if any(
        word in error
        for word in (
            "permission denied",
            "access is denied",
            "access denied",
            "unauthorized",
            "zugriff verweigert",
        )
    ):
        return "runner_docker_check_unconfirmed"
    if any(
        word in error
        for word in (
            "connection refused",
            "is the docker daemon running",
            "docker desktop is not running",
        )
    ):
        return "runner_docker_unavailable"
    if "no such file or directory" in error and (
        "docker.sock" in error or "docker_engine" in error
    ):
        return "runner_docker_unavailable"
    if any(
        text in error
        for text in (
            "cannot find the file specified",
            "das system kann die angegebene datei nicht finden",
        )
    ) and any(
        pipe in error
        for pipe in (
            "docker_engine",
            "dockerdesktoplinuxengine",
            "dockerdesktopwindowsengine",
        )
    ):
        return "runner_docker_unavailable"
    return "runner_docker_check_unconfirmed"
