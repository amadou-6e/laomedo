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
import subprocess
import sys
import tempfile

from .github_mediation import KnownRejected


_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_SHA = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?\Z")


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
        self.run = run

    def _run_git(self, directory: Path, *args: str, env: dict | None = None):
        return self.run(["git", "-C", str(directory), *args],
                        capture_output=True, check=False, env=env)

    def _git(self, *args: str, env: dict | None = None):
        return self._run_git(self.checkout, *args, env=env)

    def _valid_commit(self, commit: str) -> bool:
        if not isinstance(commit, str) or not _SHA.fullmatch(commit):
            return False
        result = self._git("cat-file", "-t", commit)
        return result.returncode == 0 and result.stdout.strip() == b"commit"

    def classify_workflow_diff(self, repository: str, branch: str,
                               commit: str) -> bool | None:
        """Fail closed unless the exact outgoing history is inspectable."""
        if repository != self.repository or not self._valid_commit(commit) or \
                not self._valid_commit(self.baseline):
            return None
        ancestor = self._git("merge-base", "--is-ancestor", self.baseline, commit)
        if ancestor.returncode != 0:
            return None
        changed = self._git("diff", "--no-ext-diff", "--no-textconv",
                            "--name-only", "-z", "--no-renames",
                            self.baseline, commit)
        if changed.returncode != 0:
            return None
        return any(path.startswith(b".github/workflows/") for path in
                   changed.stdout.split(b"\0") if path)

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
        if self._git("check-ref-format", ref).returncode != 0:
            raise KnownRejected("push_branch_invalid")
        if not self._valid_commit(commit) or self.classify_workflow_diff(
                repository, branch, commit) is not False:
            raise KnownRejected("push_commit_unverified")
        if not isinstance(connection_id, str) or not connection_id or \
                type(connection_generation) is not int or connection_generation < 1:
            raise KnownRejected("connection_binding_required")
        try:
            token = self.token_supplier(connection_id, connection_generation)
        except (KeyError, TypeError, ValueError):
            raise KnownRejected("provider_credential_unavailable") from None
        if not isinstance(token, str) or not token or "\n" in token or "\r" in token:
            raise KnownRejected("provider_credential_unavailable")

        # Empty global/system config prevents Git Credential Manager, host gh,
        # URL rewrites and inherited helpers from supplying a broader identity.
        helper = Path(__file__).with_name("git_credential_helper.py")
        helper_command = "!" + shlex.quote(sys.executable) + " " + shlex.quote(str(helper))
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(("GIT_CONFIG_", "GCM_")) and
                       key not in {"GH", "GH_TOKEN", "GITHUB_TOKEN", "GIT_ASKPASS",
                                   "SSH_ASKPASS", "GIT_SSH", "GIT_SSH_COMMAND"}}
        environment.update({
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": "",
            "LAOMEDO_MEDIATED_GIT_TOKEN": token,
        })
        remote = "https://github.com/" + repository + ".git"
        try:
            # Never run the network push from the agent-controlled checkout:
            # its local Git config could rewrite the remote URL or install an
            # unexpected credential helper. Transfer only the exact object to
            # a fresh bare repository with no checkout config or hooks.
            with tempfile.TemporaryDirectory(prefix="laomedo-git-push-") as scratch:
                bare = Path(scratch)
                initialized = self._run_git(bare, "init", "--bare", "--quiet",
                                            env=environment)
                if initialized.returncode != 0:
                    raise KnownRejected("push_staging_failed")
                fetched = self._run_git(bare, "fetch", "--no-tags", "--no-write-fetch-head",
                                        str(self.checkout), commit, env=environment)
                if fetched.returncode != 0:
                    raise KnownRejected("push_staging_failed")
                pushed = self._run_git(
                    bare, "-c", "credential.helper=", "-c",
                    "credential.helper=" + helper_command,
                    "push", "--porcelain", "--force-with-lease=" + ref + ":",
                    remote, commit + ":" + ref, env=environment)
        finally:
            environment.pop("LAOMEDO_MEDIATED_GIT_TOKEN", None)
        if pushed.returncode != 0:
            # A lost response can follow a successful remote write.
            raise RuntimeError("push_outcome_unknown")
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
