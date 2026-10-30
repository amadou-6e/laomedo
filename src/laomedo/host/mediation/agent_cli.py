"""Materialize trusted command wrappers; never install into the host PATH."""

from pathlib import Path
from laomedo.git.command import GitCommandRunner
from laomedo.git.errors import GitCommandTimeout
from laomedo.git.models import GitEnvironmentProfile, GitExecutionContext
from laomedo.git.repository import GitRepository
from laomedo.agents.interface.errors import GitWorkspaceError
import re


def prepare_commands(root: Path, repository: str, branch: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("repository_invalid")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./-]{0,127}", branch) or ".." in branch:
        raise ValueError("branch_invalid")
    destination = root / "mediated-bin"
    destination.mkdir(exist_ok=True)
    if destination.is_symlink() or set(path.name for path in destination.iterdir()) - {
        "gh",
        "git-remote-laomedo",
    }:
        raise ValueError("command_directory_invalid")
    for name, script in (("gh", "gh.mjs"), ("git-remote-laomedo", "git-remote.mjs")):
        # Generate LF even on Windows; Docker's executable mount mode is checked
        # separately. These wrappers carry no credentials or caller content.
        path = destination / name
        content = "#!/bin/sh\nexec node /run/laomedo/" + script + ' "$@"\n'
        if path.exists() or path.is_symlink():
            if (
                path.is_symlink()
                or not path.is_file()
                or path.read_bytes() != content.encode("ascii")
            ):
                raise ValueError("command_wrapper_changed")
        else:
            with path.open("x", encoding="ascii", newline="\n") as output:
                output.write(content)
        path.chmod(0o755)
    return destination


def configure_remote(workspace: Path, repository: str) -> None:
    """Read/write only the fixed remote with isolated host Git configuration."""
    runner = GitCommandRunner()
    with runner.isolated_home(
        GitEnvironmentProfile.WORKSPACE, prefix="laomedo-cli-home-"
    ) as home:
        git = GitRepository(
            workspace,
            runner=runner,
            context=GitExecutionContext(
                profile=GitEnvironmentProfile.WORKSPACE, home=home, hardened=True
            ),
        )

        def run(*args):
            try:
                return git.run(list(args))
            except GitCommandTimeout as error:
                raise GitWorkspaceError(error.code) from error

        remote = run("config", "--local", "--get-all", "remote.origin.url")
        expected = "laomedo::" + repository
        if remote.returncode == 0:
            if (
                remote.stdout.decode().splitlines() != [expected]
                or run(
                    "config", "--local", "--get-all", "remote.origin.pushurl"
                ).returncode
                != 1
            ):
                raise ValueError("mediated_remote_changed")
        elif remote.returncode == 1:
            if run("remote", "add", "origin", expected).returncode:
                raise ValueError("mediated_remote_install_failed")
        else:
            raise ValueError("mediated_remote_invalid")
        # Only host-private exclude metadata; do not alter project .gitignore.
        exclude = workspace / ".git" / "info" / "exclude"
        if exclude.is_symlink() or not exclude.is_file():
            raise ValueError("git_exclude_invalid")
        content = exclude.read_bytes()
        rule = b"/.laomedo-handoff.bundle"
        if rule not in content.splitlines():
            with exclude.open("ab") as output:
                output.write(b"\n" + rule + b"\n")
