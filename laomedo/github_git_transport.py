"""Host-only exact-commit Git push for a selected, mediated connection.

The checkout and baseline are trusted service configuration. The agent may
request a commit and its approved branch, but cannot choose the checkout,
remote, credential source, or Git command. Git failures after dispatch are
uncertain effects: never automatically retry them.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shlex
import signal
import stat
import subprocess
import sys
import tempfile

from .github_mediation import KnownRejected


_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_SHA = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?\Z")
GIT_COMMAND_TIMEOUT_SECONDS = 30
GIT_TREE_CLEANUP_SECONDS = 5


def _redirected_path(path: Path) -> bool:
    """Treat links and Windows reparse points as external object sources."""
    try:
        status = path.lstat()
    except OSError:
        return True
    return path.is_symlink() or bool(
        getattr(status, "st_file_attributes", 0) &
        getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


class GitTreeTimeout(subprocess.TimeoutExpired):
    """A timeout with an explicit tree-cleanup verification result."""

    def __init__(self, args: list[str], timeout: float, cleanup_verified: bool):
        super().__init__(args, timeout)
        self.cleanup_verified = cleanup_verified


def _run_bounded_tree(args: list[str], *, capture_output: bool, check: bool,
                      timeout: float, env: dict):
    """Bound a Git command and its descendants without a shell or host login."""
    if not capture_output or check:
        raise ValueError("git_runner_options_invalid")
    options = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE,
               "env": env}
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
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    check=False, timeout=GIT_TREE_CLEANUP_SECONDS)
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
            process.communicate(timeout=GIT_TREE_CLEANUP_SECONDS)
        except subprocess.TimeoutExpired:
            # Do not wait forever for a child that inherited an output pipe.
            for pipe in (process.stdout, process.stderr):
                if pipe is not None:
                    pipe.close()
            try:
                process.wait(timeout=GIT_TREE_CLEANUP_SECONDS)
            except subprocess.TimeoutExpired:
                cleanup_verified = False
        raise GitTreeTimeout(args, timeout, cleanup_verified) from None
    return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)


class PushOutcomeUnknown(RuntimeError):
    """A nonzero Git exit; its remote effect remains unknown regardless of hint."""

    def __init__(self, category: str, exit_code: int | None):
        super().__init__("push_outcome_unknown")
        self.category = category
        self.exit_code = exit_code


def _push_failure_category(stderr: bytes, stdout: bytes = b"") -> str:
    """Return only a fixed diagnostic label, never Git's untrusted output."""
    lower = (stderr + b"\n" + stdout).lower()
    if any(marker in lower for marker in (
            b"authentication failed", b"http 403", b"error: 403",
            b"403 forbidden", b"permission denied", b"permission to",
            b"could not read username")):
        return "authentication_or_authorization"
    if b"remote rejected" in lower or b"pre-receive hook declined" in lower:
        return "remote_rejected"
    if any(marker in lower for marker in (
            b"could not resolve host", b"timed out", b"failed to connect",
            b"connection reset", b"network is unreachable")):
        return "network_or_transport"
    return "unclassified"


def _base_git_environment() -> dict:
    """Remove inherited Git and host-account overrides for every Git call."""
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith(("GIT_", "GCM_")) and
                   key not in {"GH", "GH_TOKEN", "GITHUB_TOKEN", "GIT_ASKPASS",
                               "SSH_ASKPASS", "GIT_SSH", "GIT_SSH_COMMAND"}}
    environment.update({
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "",
        "GIT_NO_REPLACE_OBJECTS": "1",
    })
    return environment


def _credential_environment(token: str) -> tuple[dict, str]:
    """Host-only Git environment without ambient credential/config sources."""
    helper = Path(__file__).with_name("git_credential_helper.py")
    command = "!" + shlex.quote(sys.executable) + " " + shlex.quote(str(helper))
    environment = _base_git_environment()
    environment.update({
        "LAOMEDO_MEDIATED_GIT_TOKEN": token,
    })
    return environment, command


class GitHubGitTransport:
    """Push a locally present commit to a new remote branch, without host login."""

    def __init__(self, repository: str, checkout: str | Path, baseline: str,
                 token_supplier, *, run=subprocess.run):
        if not isinstance(repository, str) or not _REPOSITORY.fullmatch(repository):
            raise ValueError("repository_invalid")
        if not isinstance(baseline, str) or not _SHA.fullmatch(baseline):
            raise ValueError("baseline_invalid")
        checkout = Path(checkout).resolve()
        if not checkout.is_dir() or checkout.is_symlink():
            raise ValueError("checkout_invalid")
        if token_supplier is None:
            raise ValueError("credential_supplier_required")
        self.repository = repository
        self.checkout = checkout
        self.baseline = baseline
        self.token_supplier = token_supplier
        self.run = _run_bounded_tree if run is subprocess.run else run

    def _run_git(self, directory: Path, *args: str, env: dict | None = None):
        # Git 2.31 on Windows does not honor GIT_CONFIG_GLOBAL. Isolate both
        # home-based config locations for each child command, including the
        # credential helper, rather than relying on that override alone.
        with tempfile.TemporaryDirectory(prefix="laomedo-git-home-") as home:
            isolated = (env if env is not None else _base_git_environment()).copy()
            isolated.update({"HOME": home, "USERPROFILE": home,
                             "XDG_CONFIG_HOME": home})
            isolated.pop("HOMEDRIVE", None)
            isolated.pop("HOMEPATH", None)
            return self.run(["git", "-C", str(directory), *args],
                            capture_output=True, check=False,
                            timeout=GIT_COMMAND_TIMEOUT_SECONDS,
                            env=isolated)

    def _git(self, *args: str, env: dict | None = None):
        return self._run_git(self.checkout, *args, env=env)

    def _valid_commit(self, commit: str) -> bool:
        if not isinstance(commit, str) or not _SHA.fullmatch(commit):
            return False
        result = self._git("cat-file", "-t", commit)
        return result.returncode == 0 and result.stdout.strip() == b"commit"

    def _plain_object_source(self) -> bool:
        """Refuse Git metadata that redirects staging outside the checkout.

        The source checkout can be writable by the agent. Git's upload-pack
        follows objects/info/alternates and linked-worktree gitdir pointers,
        so a staged commit alone does not prove its objects came from the
        selected checkout. This is a preflight refusal, not an OS ownership
        boundary against a concurrent same-user mutation.
        """
        git_dir = self.checkout / ".git"
        objects = git_dir / "objects"
        info = objects / "info"
        pack = objects / "pack"
        if any(not path.is_dir() or _redirected_path(path)
               for path in (git_dir, objects, info, pack)):
            return False
        if (git_dir / "commondir").exists() or (git_dir / "commondir").is_symlink():
            return False
        alternates = info / "alternates"
        if alternates.exists() or alternates.is_symlink():
            return False
        errors = []
        for root, directories, files in os.walk(
                objects, topdown=True, followlinks=False, onerror=errors.append):
            for name in directories + files:
                if _redirected_path(Path(root) / name):
                    return False
        return not errors

    def _stage(self, bare: Path, commit: str) -> bool:
        """Fetch real objects into an isolated repository, without credentials."""
        if not self._plain_object_source():
            return False
        environment = _base_git_environment()
        try:
            if self._run_git(bare, "init", "--bare", "--quiet", env=environment).returncode:
                return False
            fetched = self._run_git(bare, "fetch", "--no-tags", "--no-write-fetch-head",
                                    str(self.checkout), commit, env=environment)
            return fetched.returncode == 0
        except subprocess.TimeoutExpired:
            # No provider credential exists yet; fail closed before a push.
            return False

    def _classify_staged(self, bare: Path, commit: str) -> bool | None:
        environment = _base_git_environment()
        try:
            if self._run_git(bare, "cat-file", "-t", commit,
                             env=environment).stdout.strip() != b"commit":
                return None
            ancestor = self._run_git(bare, "merge-base", "--is-ancestor",
                                     self.baseline, commit, env=environment)
            if ancestor.returncode != 0:
                return None
            changed = self._run_git(bare, "diff", "--no-ext-diff", "--no-textconv",
                                    "--name-only", "-z", "--no-renames",
                                    self.baseline, commit, env=environment)
            if changed.returncode != 0:
                return None
        except subprocess.TimeoutExpired:
            # Classification uses only local objects, before provider contact.
            return None
        return any(path.startswith(b".github/workflows/") for path in
                   changed.stdout.split(b"\0") if path)

    def classify_workflow_diff(self, repository: str, branch: str,
                               commit: str) -> bool | None:
        """Fail closed unless the exact outgoing history is inspectable."""
        if repository != self.repository or not isinstance(commit, str) or \
                not _SHA.fullmatch(commit):
            return None
        with tempfile.TemporaryDirectory(prefix="laomedo-git-check-") as scratch:
            bare = Path(scratch)
            if not self._stage(bare, commit):
                return None
            return self._classify_staged(bare, commit)

    def __call__(self, repository: str, operation: str, payload: dict, *,
                 connection_id: str | None = None,
                 connection_generation: int | None = None) -> dict:
        if repository != self.repository:
            raise KnownRejected("repository_denied")
        if operation != "git_push":
            raise KnownRejected("operation_not_implemented")
        branch, commit = payload.get("branch"), payload.get("commit")
        if not isinstance(branch, str) or not branch or branch.startswith("refs/"):
            raise KnownRejected("push_branch_invalid")
        ref = "refs/heads/" + branch
        try:
            branch_valid = self._git("check-ref-format", ref).returncode == 0
        except subprocess.TimeoutExpired:
            branch_valid = False
        if not branch_valid:
            raise KnownRejected("push_branch_invalid")
        if not isinstance(commit, str) or not _SHA.fullmatch(commit):
            raise KnownRejected("push_commit_unverified")
        if not isinstance(connection_id, str) or not connection_id or \
                type(connection_generation) is not int or connection_generation < 1:
            raise KnownRejected("connection_binding_required")
        remote = "https://github.com/" + repository + ".git"
        # Never inspect the agent-writable checkout for workflow approval:
        # replace refs or alternates there can describe different objects from
        # those sent by upload-pack. Classify the very staging repository that
        # will push, and do not expose the provider token during the fetch.
        with tempfile.TemporaryDirectory(prefix="laomedo-git-push-") as scratch:
            bare = Path(scratch)
            if not self._stage(bare, commit) or \
                    self._classify_staged(bare, commit) is not False:
                raise KnownRejected("push_commit_unverified")
            try:
                token = self.token_supplier(connection_id, connection_generation)
            except (KeyError, TypeError, ValueError):
                raise KnownRejected("provider_credential_unavailable") from None
            if not isinstance(token, str) or not token or "\n" in token or "\r" in token:
                raise KnownRejected("provider_credential_unavailable")
            environment, helper_command = _credential_environment(token)
            try:
                try:
                    pushed = self._run_git(
                        bare, "-c", "credential.helper=", "-c",
                        "credential.helper=" + helper_command,
                        "push", "--porcelain", "--force-with-lease=" + ref + ":",
                        remote, commit + ":" + ref, env=environment)
                except subprocess.TimeoutExpired as error:
                    # The remote may have accepted the push before Git was killed.
                    category = ("timeout" if getattr(error, "cleanup_verified", None)
                                is True else "timeout_cleanup_unverified")
                    raise PushOutcomeUnknown(category, None) from None
            finally:
                environment.pop("LAOMEDO_MEDIATED_GIT_TOKEN", None)
        if pushed.returncode != 0:
            # A lost response can follow a successful remote write.
            raise PushOutcomeUnknown(_push_failure_category(pushed.stderr,
                                                             pushed.stdout),
                                     pushed.returncode)
        return {"branch": branch, "commit": commit}


class GitHubMediatedTransport:
    """Route Git pushes and supported REST calls through one selected identity."""

    def __init__(self, git_transport: GitHubGitTransport, rest_transport):
        if git_transport.repository != rest_transport.repository:
            raise ValueError("repository_mismatch")
        self.git = git_transport
        self.rest = rest_transport

    def __call__(self, repository: str, operation: str, payload: dict, **binding):
        target = self.git if operation == "git_push" else self.rest
        return target(repository, operation, payload, **binding)
