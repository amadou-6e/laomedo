"""Host-only exact-commit Git push for a selected, mediated connection.

The checkout and baseline are trusted service configuration. The agent may
request a commit and its approved branch, but cannot choose the checkout,
remote, credential source, or Git command. Git failures after dispatch are
uncertain effects: never automatically retry them."""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
import base64
import laomedo.github.transport.git.constants as _git_constants
import laomedo.github.transport.git.errors as _git_errors
import laomedo.github.transport.git.utils as _git_utils
import laomedo.host.mediation.errors as _mediation_errors
import os
import re
import subprocess
import tempfile


class GitTreeTimeout(subprocess.TimeoutExpired):
    """A timeout with an explicit tree-cleanup verification result."""

    def __init__(self, args: list[str], timeout: float, cleanup_verified: bool):
        super().__init__(args, timeout)
        self.cleanup_verified = cleanup_verified


class GitHubGitTransport:
    """Push a locally present commit to a new remote branch, without host login."""

    def __init__(
        self,
        repository: str,
        checkout: str | Path,
        baseline: str,
        token_supplier,
        *,
        run=subprocess.run,
        require_verified_stage: bool = False,
    ):
        if not isinstance(repository, str) or not _git_constants._REPOSITORY.fullmatch(
            repository
        ):
            raise ValueError("repository_invalid")
        if not isinstance(baseline, str) or not _git_constants._SHA.fullmatch(baseline):
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
        self.run = _git_utils._run_bounded_tree if run is subprocess.run else run

    def _run_git(self, directory: Path, *args: str, env: dict | None = None):
        # Git 2.31 on Windows does not honor GIT_CONFIG_GLOBAL. Isolate both
        # home-based config locations for each child command, including the
        # credential helper, rather than relying on that override alone.
        with tempfile.TemporaryDirectory(
            prefix="laomedo-git-home-", ignore_cleanup_errors=True
        ) as home:
            isolated = (
                env if env is not None else _git_utils._base_git_environment()
            ).copy()
            isolated.update(
                {"HOME": home, "USERPROFILE": home, "XDG_CONFIG_HOME": home}
            )
            isolated.pop("HOMEDRIVE", None)
            isolated.pop("HOMEPATH", None)
            return self.run(
                ["git", "-C", str(directory), *args],
                capture_output=True,
                check=False,
                timeout=_git_constants.GIT_COMMAND_TIMEOUT_SECONDS,
                env=isolated,
            )

    def _git(self, *args: str, env: dict | None = None):
        return self._run_git(self.checkout, *args, env=env)

    def _valid_commit(self, commit: str) -> bool:
        if not isinstance(commit, str) or not _git_constants._SHA.fullmatch(commit):
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
        if any(
            not path.is_dir() or _git_utils._redirected_path(path)
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
                if _git_utils._redirected_path(Path(root) / name):
                    return False
        return not errors

    def _stage(self, bare: Path, commit: str) -> bool:
        """Fetch real objects into an isolated repository, without credentials."""
        if not self._plain_object_source():
            return False
        environment = _git_utils._base_git_environment()
        try:
            if self._run_git(
                bare, "init", "--bare", "--quiet", env=environment
            ).returncode:
                return False
            fetched = self._run_git(
                bare,
                "fetch",
                "--no-tags",
                "--no-write-fetch-head",
                str(self.checkout),
                commit,
                env=environment,
            )
            return fetched.returncode == 0
        except subprocess.TimeoutExpired:
            # No provider credential exists yet; fail closed before a push.
            return False

    def _classify_staged(self, bare: Path, commit: str) -> bool | None:
        environment = _git_utils._base_git_environment()
        try:
            if (
                self._run_git(
                    bare, "cat-file", "-t", commit, env=environment
                ).stdout.strip()
                != b"commit"
            ):
                return None
            ancestor = self._run_git(
                bare,
                "merge-base",
                "--is-ancestor",
                self.baseline,
                commit,
                env=environment,
            )
            if ancestor.returncode != 0:
                return None
            changed = self._run_git(
                bare,
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--name-only",
                "-z",
                "--no-renames",
                self.baseline,
                commit,
                env=environment,
            )
            if changed.returncode != 0:
                return None
        except subprocess.TimeoutExpired:
            # Classification uses only local objects, before provider contact.
            return None
        return any(
            path.startswith(b".github/workflows/")
            for path in changed.stdout.split(b"\0")
            if path
        )

    def classify_workflow_diff(
        self, repository: str, branch: str, commit: str
    ) -> bool | None:
        """Fail closed unless the exact outgoing history is inspectable."""
        if (
            repository != self.repository
            or not isinstance(commit, str)
            or not _git_constants._SHA.fullmatch(commit)
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
            raise _mediation_errors.KnownRejected("repository_denied")
        if operation == "git_fetch":
            return self._fetch(
                payload,
                connection_id,
                connection_generation,
                allowed_branch,
                allowed_base_branch,
            )
        if operation != "git_push":
            raise _mediation_errors.KnownRejected("operation_not_implemented")
        branch, commit = payload.get("branch"), payload.get("commit")
        if not isinstance(branch, str) or not branch or branch.startswith("refs/"):
            raise _mediation_errors.KnownRejected("push_branch_invalid")
        ref = "refs/heads/" + branch
        if not isinstance(commit, str) or not _git_constants._SHA.fullmatch(commit):
            raise _mediation_errors.KnownRejected("push_commit_unverified")
        if expected_remote_commit is not None and (
            not isinstance(expected_remote_commit, str)
            or not re.fullmatch(r"[0-9a-f]{40}", expected_remote_commit)
        ):
            raise _mediation_errors.KnownRejected("push_predecessor_invalid")
        if self.require_verified_stage and verified_stage is None:
            raise _mediation_errors.KnownRejected("push_stage_required")
        if verified_stage is not None and (
            verified_stage.repository != repository
            or verified_stage.branch != branch
            or verified_stage.commit != commit
            or verified_stage.baseline != self.baseline
        ):
            raise _mediation_errors.KnownRejected("push_stage_scope_mismatch")
        if (
            not isinstance(connection_id, str)
            or not connection_id
            or type(connection_generation) is not int
            or connection_generation < 1
        ):
            raise _mediation_errors.KnownRejected("connection_binding_required")
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
                    raise _mediation_errors.KnownRejected("push_commit_unverified")
            else:
                # Local import and classification use the exact same bare
                # repository that the push below sends. Never fetch checkout
                # objects after a verified snapshot has been supplied.
                import laomedo.host.publication.verified.utils as _verified_utils
                import laomedo.host.publication.verified.errors as _verified_errors

                try:
                    staged = stack.enter_context(
                        _verified_utils.stage_verified_git(verified_stage)
                    )
                    if staged.classify_workflow_change() is not False:
                        raise _mediation_errors.KnownRejected(
                            "workflow_approval_required"
                        )
                except _verified_errors.VerifiedGitStageError as error:
                    raise _mediation_errors.KnownRejected(
                        "push_stage_invalid"
                    ) from error
                bare = staged.bare
            try:
                branch_valid = (
                    self._run_git(bare, "check-ref-format", ref).returncode == 0
                )
            except subprocess.TimeoutExpired:
                branch_valid = False
            if not branch_valid:
                raise _mediation_errors.KnownRejected("push_branch_invalid")
            if expected_remote_commit is not None:
                try:
                    fast_forward = (
                        self._run_git(
                            bare,
                            "merge-base",
                            "--is-ancestor",
                            expected_remote_commit,
                            commit,
                        ).returncode
                        == 0
                    )
                except subprocess.TimeoutExpired:
                    fast_forward = False
                if not fast_forward:
                    raise _mediation_errors.KnownRejected("push_not_fast_forward")
            try:
                token = self.token_supplier(connection_id, connection_generation)
            except (KeyError, TypeError, ValueError):
                raise _mediation_errors.KnownRejected(
                    "provider_credential_unavailable"
                ) from None
            if (
                not isinstance(token, str)
                or not token
                or "\n" in token
                or "\r" in token
            ):
                raise _mediation_errors.KnownRejected("provider_credential_unavailable")
            environment, helper_command = _git_utils._credential_environment(token)
            try:
                try:
                    pushed = self._run_git(
                        bare,
                        "-c",
                        "credential.helper=",
                        "-c",
                        "credential.helper=" + helper_command,
                        "push",
                        "--porcelain",
                        "--force-with-lease="
                        + ref
                        + ":"
                        + (expected_remote_commit or ""),
                        remote,
                        commit + ":" + ref,
                        env=environment,
                    )
                except subprocess.TimeoutExpired as error:
                    # The remote may have accepted the push before Git was killed.
                    category = (
                        "timeout"
                        if getattr(error, "cleanup_verified", None) is True
                        else "timeout_cleanup_unverified"
                    )
                    raise _git_errors.PushOutcomeUnknown(category, None) from None
            finally:
                environment.pop("LAOMEDO_MEDIATED_GIT_TOKEN", None)
        if pushed.returncode != 0:
            # A lost response can follow a successful remote write.
            raise _git_errors.PushOutcomeUnknown(
                _git_utils._push_failure_category(pushed.stderr, pushed.stdout),
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
            raise _mediation_errors.KnownRejected("connection_binding_required")
        action = payload.get("action")
        if (
            not isinstance(base_branch, str)
            or not base_branch
            or base_branch.startswith("refs/")
            or ".." in base_branch
        ):
            raise _mediation_errors.KnownRejected("fetch_ref_invalid")
        refs = {"refs/heads/" + base_branch, "refs/heads/" + branch}
        if action == "list":
            if set(payload) != {"action"}:
                raise _mediation_errors.KnownRejected("fetch_request_invalid")
        elif (
            action != "fetch"
            or set(payload) != {"action", "ref", "commit"}
            or payload.get("ref") not in refs
            or not isinstance(payload.get("commit"), str)
            or not re.fullmatch(r"[0-9a-f]{40}", payload["commit"])
        ):
            raise _mediation_errors.KnownRejected("fetch_request_invalid")
        try:
            token = self.token_supplier(connection_id, generation)
        except (KeyError, TypeError, ValueError):
            raise _mediation_errors.KnownRejected(
                "provider_credential_unavailable"
            ) from None
        if not isinstance(token, str) or not token or "\n" in token or "\r" in token:
            raise _mediation_errors.KnownRejected("provider_credential_unavailable")
        environment, helper = _git_utils._credential_environment(token)
        remote = "https://github.com/" + self.repository + ".git"
        credential = ("-c", "credential.helper=", "-c", "credential.helper=" + helper)
        try:
            with tempfile.TemporaryDirectory(prefix="laomedo-git-read-") as scratch:
                bare = Path(scratch)
                if self._run_git(
                    bare, "init", "--bare", "--template=", "--quiet"
                ).returncode:
                    raise _mediation_errors.KnownRejected("fetch_initialization_failed")
                for ref in refs:
                    if self._run_git(bare, "check-ref-format", ref).returncode:
                        raise _mediation_errors.KnownRejected("fetch_ref_invalid")
                if action == "list":
                    listed = self._run_git(
                        bare,
                        *credential,
                        "ls-remote",
                        "--heads",
                        remote,
                        *sorted(refs),
                        env=environment,
                    )
                    if listed.returncode or len(listed.stdout) > 1024:
                        raise _mediation_errors.KnownRejected("fetch_listing_failed")
                    result, seen = [], set()
                    for line in listed.stdout.decode("ascii").splitlines():
                        commit, ref = line.split("\t")
                        if (
                            not re.fullmatch(r"[0-9a-f]{40}", commit)
                            or ref not in refs
                            or ref in seen
                        ):
                            raise _mediation_errors.KnownRejected(
                                "fetch_listing_invalid"
                            )
                        seen.add(ref)
                        result.append({"ref": ref, "commit": commit})
                    return {"refs": result}
                fetched = self._run_git(
                    bare,
                    *credential,
                    "fetch",
                    "--no-tags",
                    "--no-write-fetch-head",
                    remote,
                    payload["ref"] + ":refs/heads/laomedo-read",
                    env=environment,
                )
                environment.pop("LAOMEDO_MEDIATED_GIT_TOKEN", None)
                if fetched.returncode:
                    raise _mediation_errors.KnownRejected("fetch_acquisition_failed")
                actual = self._run_git(
                    bare, "rev-parse", "refs/heads/laomedo-read^{commit}"
                )
                if (
                    actual.returncode
                    or actual.stdout.decode().strip() != payload["commit"]
                ):
                    raise _mediation_errors.KnownRejected("fetch_ref_changed")
                if self._run_git(bare, "fsck", "--full", "--strict").returncode:
                    raise _mediation_errors.KnownRejected("fetch_objects_invalid")
                bundle = bare / "read.bundle"
                if self._run_git(
                    bare, "bundle", "create", str(bundle), "refs/heads/laomedo-read"
                ).returncode:
                    raise _mediation_errors.KnownRejected("fetch_bundle_failed")
                if bundle.stat().st_size > 262144:
                    raise _mediation_errors.KnownRejected("fetch_bundle_too_large")
                data = bundle.read_bytes()
                return {
                    "ref": payload["ref"],
                    "commit": payload["commit"],
                    "bundle": base64.b64encode(data).decode("ascii"),
                }
        finally:
            environment.pop("LAOMEDO_MEDIATED_GIT_TOKEN", None)


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
