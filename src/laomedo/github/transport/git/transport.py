"""Host-only exact-commit Git push for a selected, mediated connection.

The checkout and baseline are trusted service configuration. The agent may
request a commit and its approved branch, but cannot choose the checkout,
remote, credential source, or Git command. Git failures after dispatch are
uncertain effects: never automatically retry them."""

from __future__ import annotations

from contextlib import ExitStack
from pydantic import SecretStr
from laomedo.git.command import GitCommandRunner
from laomedo.git.models import GitCredential, GitExecutionContext
from laomedo.git.repository import GitRepository
from laomedo.github.workflows.utils import touches_workflows
from pathlib import Path
import base64
from laomedo.github.transport.git.settings import _REPOSITORY
from laomedo.github.transport.git.settings import _SHA
from laomedo.github.transport.git.errors import PushOutcomeUnknown
from laomedo.github.transport.git.utils import _push_failure_category
from laomedo.github.transport.git.utils import _redirected_path
from laomedo.host.mediation.errors import KnownRejected
import os
import re
import subprocess
import tempfile





class GitHubGitTransport:
    """Push a locally present commit to a new remote branch, without host login."""

    def __init__(
        self,
        repository: str,
        checkout: str | Path,
        baseline: str,
        token_supplier,
        *,
        runner: GitCommandRunner | None = None,
        require_verified_stage: bool = False,
    ):
        if not isinstance(repository, str) or not _REPOSITORY.fullmatch(
            repository
        ):
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
        self.require_verified_stage = require_verified_stage
        self.runner = runner if runner is not None else GitCommandRunner()

    def _repository(self, directory: Path) -> GitRepository:
        """Bind generic mechanics; connection and publication policy stay here."""
        return GitRepository(directory, context=GitExecutionContext(), runner=self.runner)



    def _valid_commit(self, commit: str) -> bool:
        """Admit a commit identifier only when its local object is a commit."""
        return (isinstance(commit, str) and bool(_SHA.fullmatch(commit))
                and self._repository(self.checkout).object_type(commit) == b"commit")

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
        if any(
            not path.is_dir() or _redirected_path(path)
            for path in (git_dir, objects, info, pack)
        ):
            return False
        if (git_dir / "commondir").exists() or (git_dir / "commondir").is_symlink():
            return False
        alternates = info / "alternates"
        if alternates.exists() or alternates.is_symlink():
            return False
        errors = []
        for root, directories, files in os.walk(
            objects, topdown=True, followlinks=False, onerror=errors.append
        ):
            for name in directories + files:
                if _redirected_path(Path(root) / name):
                    return False
        return not errors

    def _stage(self, bare: Path, commit: str) -> bool:
        """Fetch real objects into an isolated repository, without credentials."""
        if not self._plain_object_source():
            return False
        repository = self._repository(bare)
        try:
            return repository.init_bare() and repository.fetch(str(self.checkout), commit)
        except subprocess.TimeoutExpired:
            # No provider credential exists yet; fail closed before a push.
            return False

    def _classify_staged(self, bare: Path, commit: str) -> bool | None:
        """Apply workflow policy to the exact object store that would be pushed."""
        repository = self._repository(bare)
        try:
            if (repository.object_type(commit) != b"commit"
                    or not repository.is_ancestor(self.baseline, commit)):
                return None
            paths = repository.changed_paths(self.baseline, commit)
        except subprocess.TimeoutExpired:
            return None
        return touches_workflows(paths) if paths is not None else None

    def classify_workflow_diff(
        self, repository: str, branch: str, commit: str
    ) -> bool | None:
        """Fail closed unless the exact outgoing history is inspectable."""
        if (
            repository != self.repository
            or not isinstance(commit, str)
            or not _SHA.fullmatch(commit)
        ):
            return None
        with tempfile.TemporaryDirectory(prefix="laomedo-git-check-") as scratch:
            bare = Path(scratch)
            if not self._stage(bare, commit):
                return None
            return self._classify_staged(bare, commit)

    def __call__(
        self,
        repository: str,
        operation: str,
        payload: dict,
        *,
        connection_id: str | None = None,
        connection_generation: int | None = None,
        verified_stage=None,
        allowed_branch: str | None = None,
        allowed_base_branch: str = "main",
        expected_remote_commit: str | None = None,
    ) -> dict:
        if repository != self.repository:
            raise KnownRejected("repository_denied")
        if operation == "git_fetch":
            return self._fetch(
                payload,
                connection_id,
                connection_generation,
                allowed_branch,
                allowed_base_branch,
            )
        if operation != "git_push":
            raise KnownRejected("operation_not_implemented")
        branch, commit = payload.get("branch"), payload.get("commit")
        if not isinstance(branch, str) or not branch or branch.startswith("refs/"):
            raise KnownRejected("push_branch_invalid")
        ref = "refs/heads/" + branch
        if not isinstance(commit, str) or not _SHA.fullmatch(commit):
            raise KnownRejected("push_commit_unverified")
        if expected_remote_commit is not None and (
            not isinstance(expected_remote_commit, str)
            or not re.fullmatch(r"[0-9a-f]{40}", expected_remote_commit)
        ):
            raise KnownRejected("push_predecessor_invalid")
        if self.require_verified_stage and verified_stage is None:
            raise KnownRejected("push_stage_required")
        if verified_stage is not None and (
            verified_stage.repository != repository
            or verified_stage.branch != branch
            or verified_stage.commit != commit
            or verified_stage.baseline != self.baseline
        ):
            raise KnownRejected("push_stage_scope_mismatch")
        if (
            not isinstance(connection_id, str)
            or not connection_id
            or type(connection_generation) is not int
            or connection_generation < 1
        ):
            raise KnownRejected("connection_binding_required")
        remote = "https://github.com/" + repository + ".git"
        # Never inspect the agent-writable checkout for workflow approval:
        # replace refs or alternates there can describe different objects from
        # those sent by upload-pack. Classify the very staging repository that
        # will push, and do not expose the provider token during the fetch.
        with ExitStack() as stack:
            if verified_stage is None:
                bare = Path(
                    stack.enter_context(
                        tempfile.TemporaryDirectory(prefix="laomedo-git-push-")
                    )
                )
                if (
                    not self._stage(bare, commit)
                    or self._classify_staged(bare, commit) is not False
                ):
                    raise KnownRejected("push_commit_unverified")
            else:
                # Local import and classification use the exact same bare
                # repository that the push below sends. Never fetch checkout
                # objects after a verified snapshot has been supplied.
                from laomedo.host.publication.verified.utils import stage_verified_git
                from laomedo.host.publication.verified.errors import VerifiedGitStageError

                try:
                    staged = stack.enter_context(
                        stage_verified_git(verified_stage, runner=self.runner)
                    )
                    if staged.classify_workflow_change() is not False:
                        raise KnownRejected(
                            "workflow_approval_required"
                        )
                except VerifiedGitStageError as error:
                    raise KnownRejected(
                        "push_stage_invalid"
                    ) from error
                bare = staged.bare
            try:
                branch_valid = (
                    self._repository(bare).check_ref_format(ref)
                )
            except subprocess.TimeoutExpired:
                branch_valid = False
            if not branch_valid:
                raise KnownRejected("push_branch_invalid")
            if expected_remote_commit is not None:
                try:
                    fast_forward = (
                        self._repository(bare).is_ancestor(expected_remote_commit, commit)
                    )
                except subprocess.TimeoutExpired:
                    fast_forward = False
                if not fast_forward:
                    raise KnownRejected("push_not_fast_forward")
            try:
                token = self.token_supplier(connection_id, connection_generation)
            except (KeyError, TypeError, ValueError):
                raise KnownRejected(
                    "provider_credential_unavailable"
                ) from None
            if (
                not isinstance(token, str)
                or not token
                or "\n" in token
                or "\r" in token
            ):
                raise KnownRejected("provider_credential_unavailable")
            credential = GitCredential(token=SecretStr(token))
            try:
                pushed = self._repository(bare).run(
                    ["push", "--porcelain",
                     "--force-with-lease=" + ref + ":" + (expected_remote_commit or ""),
                     remote, commit + ":" + ref], credential=credential)
            except subprocess.TimeoutExpired as error:
                # The remote may have accepted the push before Git was killed.
                category = ("timeout" if getattr(error, "cleanup_verified", None) is True
                            else "timeout_cleanup_unverified")
                raise PushOutcomeUnknown(category, None) from None
        if pushed.returncode != 0:
            # A lost response can follow a successful remote write.
            raise PushOutcomeUnknown(
                _push_failure_category(pushed.stderr, pushed.stdout),
                pushed.returncode,
            )
        result = {"branch": branch, "commit": commit}
        if verified_stage is not None:
            result["stage_digest"] = verified_stage.stage_digest
        return result

    def _fetch(
        self,
        payload: dict,
        connection_id: str | None,
        generation: int | None,
        branch: str | None,
        base_branch: str,
    ) -> dict:
        """Read selected refs with host custody; bound returned bytes, not disk."""
        if (
            not isinstance(branch, str)
            or not branch
            or not isinstance(connection_id, str)
            or not connection_id
            or type(generation) is not int
            or generation < 1
        ):
            raise KnownRejected("connection_binding_required")
        action = payload.get("action")
        if (
            not isinstance(base_branch, str)
            or not base_branch
            or base_branch.startswith("refs/")
            or ".." in base_branch
        ):
            raise KnownRejected("fetch_ref_invalid")
        refs = {"refs/heads/" + base_branch, "refs/heads/" + branch}
        if action == "list":
            if set(payload) != {"action"}:
                raise KnownRejected("fetch_request_invalid")
        elif (
            action != "fetch"
            or set(payload) != {"action", "ref", "commit"}
            or payload.get("ref") not in refs
            or not isinstance(payload.get("commit"), str)
            or not re.fullmatch(r"[0-9a-f]{40}", payload["commit"])
        ):
            raise KnownRejected("fetch_request_invalid")
        try:
            token = self.token_supplier(connection_id, generation)
        except (KeyError, TypeError, ValueError):
            raise KnownRejected(
                "provider_credential_unavailable"
            ) from None
        if not isinstance(token, str) or not token or "\n" in token or "\r" in token:
            raise KnownRejected("provider_credential_unavailable")
        credential = GitCredential(token=SecretStr(token))
        remote = "https://github.com/" + self.repository + ".git"
        with tempfile.TemporaryDirectory(prefix="laomedo-git-read-") as scratch:
            bare = Path(scratch)
            repository = self._repository(bare)
            if not repository.init_bare(empty_template=True):
                raise KnownRejected("fetch_initialization_failed")
            for ref in refs:
                if not repository.check_ref_format(ref):
                    raise KnownRejected("fetch_ref_invalid")
            if action == "list":
                listed = repository.run(["ls-remote", "--heads", remote, *sorted(refs)],
                                        credential=credential)
                if listed.returncode or len(listed.stdout) > 1024:
                    raise KnownRejected("fetch_listing_failed")
                result, seen = [], set()
                for line in listed.stdout.decode("ascii").splitlines():
                    commit, ref = line.split("\t")
                    if (not re.fullmatch(r"[0-9a-f]{40}", commit)
                            or ref not in refs or ref in seen):
                        raise KnownRejected("fetch_listing_invalid")
                    seen.add(ref)
                    result.append({"ref": ref, "commit": commit})
                return {"refs": result}
            if not repository.fetch(remote, payload["ref"] + ":refs/heads/laomedo-read",
                                    credential=credential):
                raise KnownRejected("fetch_acquisition_failed")
            actual = repository.resolve("refs/heads/laomedo-read^{commit}")
            if actual != payload["commit"].encode("ascii"):
                raise KnownRejected("fetch_ref_changed")
            if not repository.fsck():
                raise KnownRejected("fetch_objects_invalid")
            bundle = bare / "read.bundle"
            if repository.run(["bundle", "create", str(bundle), "refs/heads/laomedo-read"]).returncode:
                raise KnownRejected("fetch_bundle_failed")
            if bundle.stat().st_size > 262144:
                raise KnownRejected("fetch_bundle_too_large")
            return {"ref": payload["ref"], "commit": payload["commit"],
                    "bundle": base64.b64encode(bundle.read_bytes()).decode("ascii")}



class GitHubMediatedTransport:
    """Route Git pushes and supported REST calls through one selected identity."""

    def __init__(self, git_transport: GitHubGitTransport, rest_transport):
        if git_transport.repository != rest_transport.repository:
            raise ValueError("repository_mismatch")
        self.git = git_transport
        self.rest = rest_transport

    def __call__(self, repository: str, operation: str, payload: dict, **binding):
        target = self.git if operation in {"git_push", "git_fetch"} else self.rest
        return target(repository, operation, payload, **binding)
