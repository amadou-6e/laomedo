"""Implementation owned by github / transport / git / utils."""

from __future__ import annotations

from pathlib import Path
import laomedo._paths as _package_paths
import laomedo.github.transport.git.constants as _git_constants
import os
import shlex
import signal
import stat
import subprocess
import sys


def _redirected_path(path: Path) -> bool:
    """Treat links and Windows reparse points as external object sources."""
    try:
        status = path.lstat()
    except OSError:
        return True
    return path.is_symlink() or bool(
        getattr(status, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _run_bounded_tree(
    args: list[str], *, capture_output: bool, check: bool, timeout: float, env: dict
):
    """Bound a Git command and its descendants without a shell or host login."""
    import laomedo.github.transport.git.transport as _git_transport

    if not capture_output or check:
        raise ValueError("git_runner_options_invalid")
    options = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "env": env}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    process = subprocess.Popen(args, **options)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        # Kill while the parent still exists so taskkill can enumerate its
        # descendants. A bare Popen.kill() would strand git-remote-https.
        cleanup_verified = False
        if os.name == "nt":
            try:
                killed = subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=_git_constants.GIT_TREE_CLEANUP_SECONDS,
                )
                cleanup_verified = killed.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                pass
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
                cleanup_verified = True
            except OSError:
                pass
        if process.poll() is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        try:
            process.communicate(timeout=_git_constants.GIT_TREE_CLEANUP_SECONDS)
        except subprocess.TimeoutExpired:
            # Do not wait forever for a child that inherited an output pipe.
            for pipe in (process.stdout, process.stderr):
                if pipe is not None:
                    pipe.close()
            try:
                process.wait(timeout=_git_constants.GIT_TREE_CLEANUP_SECONDS)
            except subprocess.TimeoutExpired:
                cleanup_verified = False
        raise _git_transport.GitTreeTimeout(args, timeout, cleanup_verified) from None
    return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)


def _push_failure_category(stderr: bytes, stdout: bytes = b"") -> str:
    """Return only a fixed diagnostic label, never Git's untrusted output."""
    lower = (stderr + b"\n" + stdout).lower()
    if any(
        marker in lower
        for marker in (
            b"authentication failed",
            b"http 403",
            b"error: 403",
            b"403 forbidden",
            b"permission denied",
            b"permission to",
            b"could not read username",
        )
    ):
        return "authentication_or_authorization"
    if b"remote rejected" in lower or b"pre-receive hook declined" in lower:
        return "remote_rejected"
    if any(
        marker in lower
        for marker in (
            b"could not resolve host",
            b"timed out",
            b"failed to connect",
            b"connection reset",
            b"network is unreachable",
        )
    ):
        return "network_or_transport"
    return "unclassified"


def _base_git_environment() -> dict:
    """Remove inherited Git and host-account overrides for every Git call."""
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GIT_", "GCM_"))
        and key
        not in {
            "GH",
            "GH_TOKEN",
            "GITHUB_TOKEN",
            "GIT_ASKPASS",
            "SSH_ASKPASS",
            "GIT_SSH",
            "GIT_SSH_COMMAND",
        }
    }
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "",
            "GIT_NO_REPLACE_OBJECTS": "1",
        }
    )
    return environment


def _credential_environment(token: str) -> tuple[dict, str]:
    """Host-only Git environment without ambient credential/config sources."""
    helper = Path(
        _package_paths.package_root(), "host", "credentials", "git_credential_helper.py"
    )
    command = "!" + shlex.quote(sys.executable) + " " + shlex.quote(str(helper))
    environment = _base_git_environment()
    environment.update(
        {
            "LAOMEDO_MEDIATED_GIT_TOKEN": token,
        }
    )
    return environment, command
