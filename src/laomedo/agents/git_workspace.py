"""Prepare an opt-in, credential-free whole-repository agent checkout.

This helper does not grant a mediated push. A controller must still bind the
run and its bundle artifact to a trusted mediator before enabling that action.
The existing file-snapshot runner path remains unchanged.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile

_SHA = re.compile(rb"[0-9a-f]{40}\Z")
GIT_COMMAND_TIMEOUT_SECONDS = 30


class GitWorkspaceError(RuntimeError):
    """An opt-in Git checkout failed closed before agent dispatch."""


def _git_environment(home: str) -> dict[str, str]:
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith(("GIT_", "GCM_")) and
                   key not in {"GH", "GH_TOKEN", "GITHUB_TOKEN", "SSH_ASKPASS"}}
    environment.update({"HOME": home, "USERPROFILE": home,
                        "XDG_CONFIG_HOME": home,
                        "GIT_CONFIG_GLOBAL": os.devnull,
                        "GIT_CONFIG_SYSTEM": os.devnull,
                        "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
                        "GIT_NO_REPLACE_OBJECTS": "1",
                        "GIT_OPTIONAL_LOCKS": "0",
                        "GIT_LFS_SKIP_SMUDGE": "1"})
    environment.pop("HOMEDRIVE", None)
    environment.pop("HOMEPATH", None)
    return environment


def _bounded_git(args: list[str], env: dict[str, str]):
    options = {"stdin": subprocess.DEVNULL, "stdout": subprocess.PIPE,
               "stderr": subprocess.PIPE, "env": env}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    process = subprocess.Popen(args, **options)
    try:
        stdout, stderr = process.communicate(timeout=GIT_COMMAND_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as error:
        cleanup_verified = False
        if os.name == "nt":
            try:
                killed = subprocess.run(["taskkill", "/PID", str(process.pid),
                                         "/T", "/F"], check=False,
                                        stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL, timeout=5)
                cleanup_verified = killed.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                pass
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
                cleanup_verified = True
            except OSError:
                pass
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            cleanup_verified = False
        raise GitWorkspaceError("git_timeout" if cleanup_verified else
                                "git_timeout_cleanup_unverified") from error
    return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)


def prepare_git_workspace(source: Path, destination: Path) -> str:
    """Clone a clean, real repository into a new run workspace without login.

    The returned baseline is a trusted host observation, not an agent claim.
    Source must be a trusted host repository root, never agent output or a
    previous run workspace. Worktrees, gitlinks, symlinks, sparse checkouts
    and an uncommitted source are refused.
    """
    if source.is_symlink() or destination.exists() or destination.is_symlink():
        raise GitWorkspaceError("git_workspace_path_invalid")
    source = source.expanduser().resolve()
    git_dir = source / ".git"
    if not source.is_dir() or not git_dir.is_dir() or git_dir.is_symlink():
        raise GitWorkspaceError("git_repository_root_required")
    with tempfile.TemporaryDirectory(prefix="laomedo-git-home-") as home:
        env = _git_environment(home)

        def command(*args: str, cwd: Path | None = None, source_side: bool = False):
            argv = ["git"]
            if source_side:
                argv.extend(["-c", "core.fsmonitor=false",
                             "-c", f"core.hooksPath={home}"])
            if cwd is not None:
                argv.extend(["-C", str(cwd)])
            argv.extend(args)
            return _bounded_git(argv, env)

        baseline = command("rev-parse", "--verify", "HEAD", cwd=source,
                           source_side=True)
        if baseline.returncode or not _SHA.fullmatch(baseline.stdout.strip()):
            raise GitWorkspaceError("source_commit_invalid")
        indexed = command("ls-files", "--stage", "-z", cwd=source,
                          source_side=True)
        if indexed.returncode:
            raise GitWorkspaceError("source_index_invalid")
        modes = {row.split(b" ", 1)[0] for row in indexed.stdout.split(b"\0") if row}
        if b"160000" in modes:
            raise GitWorkspaceError("submodule_source_unsupported")
        if b"120000" in modes:
            raise GitWorkspaceError("symlink_source_unsupported")
        if any((path := row.split(b"\t", 1)[-1].replace(b"\\", b"/").lower())
               == b".agents/skills" or path.startswith(b".agents/skills/")
               for row in indexed.stdout.split(b"\0") if row):
            raise GitWorkspaceError("tracked_skill_path_unsupported")
        config = command("config", "--local", "--get", "core.sparseCheckout",
                         cwd=source, source_side=True)
        if config.returncode == 0 and config.stdout.strip().lower() in {b"true", b"1", b"yes"}:
            raise GitWorkspaceError("sparse_source_unsupported")
        status = command("status", "--porcelain=v1", "--untracked-files=all",
                         cwd=source, source_side=True)
        if status.returncode or status.stdout:
            raise GitWorkspaceError("source_not_clean")
        try:
            destination.mkdir()
        except FileExistsError as error:
            raise GitWorkspaceError("git_workspace_path_invalid") from error
        try:
            cloned = command("clone", "--no-local", "--no-hardlinks", "--no-checkout",
                             "--single-branch", "--quiet", str(source), str(destination))
            if cloned.returncode:
                raise GitWorkspaceError("git_clone_failed")
            sha = baseline.stdout.decode("ascii").strip()
            checked = command("checkout", "--quiet", "--detach", sha, cwd=destination)
            if checked.returncode:
                raise GitWorkspaceError("git_checkout_failed")
            removed = command("remote", "remove", "origin", cwd=destination)
            if removed.returncode:
                raise GitWorkspaceError("git_remote_removal_failed")
            tracked_skills = command("ls-files", "-z", "--", ".agents/skills",
                                     cwd=destination)
            if tracked_skills.returncode or tracked_skills.stdout:
                raise GitWorkspaceError("tracked_skill_path_unsupported")
            with (destination / ".git" / "info" / "exclude").open("a", encoding="utf-8",
                                                             newline="\n") as exclusions:
                exclusions.write("\n/.agents/skills/\n")
            final = command("rev-parse", "--verify", "HEAD", cwd=destination)
            remotes = command("remote", cwd=destination)
            if final.returncode or final.stdout.strip() != baseline.stdout.strip() or \
                    remotes.returncode or remotes.stdout.strip():
                raise GitWorkspaceError("git_clone_verification_failed")
            return sha
        except BaseException:
            try:
                if destination.exists():
                    shutil.rmtree(destination)
            except OSError as cleanup_error:
                raise GitWorkspaceError("git_workspace_cleanup_unverified") from cleanup_error
            raise
