"""Synthetic end-to-end grant, exact-commit push, and selective revocation."""

from pathlib import Path
import subprocess
import tempfile
import unittest

from laomedo.github_git_transport import GitHubGitTransport
from laomedo.github_mediation import MediationError, MediationStore
from laomedo.host_token_connection import HostTokenConnection


class HostMediatedPushTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.path = Path(self.root.name)
        self.checkout = self.path / "checkout"
        self.checkout.mkdir()
        self._git("init", "-q")
        self._git("config", "user.name", "Test")
        self._git("config", "user.email", "test@example.invalid")
        (self.checkout / "marker.txt").write_text("base\n", encoding="utf-8")
        self._git("add", "marker.txt")
        self._git("commit", "-qm", "base")
        baseline = self._git("rev-parse", "HEAD").stdout.decode().strip()
        (self.checkout / "marker.txt").write_text("changed\n", encoding="utf-8")
        self._git("commit", "-qam", "changed")
        self.commit = self._git("rev-parse", "HEAD").stdout.decode().strip()
        token_file = self.path / "host.env"
        token_file.write_text("GH=synthetic-provider-token\n", encoding="utf-8")
        self.token_file = token_file
        self.connection = HostTokenConnection(
            connection_id="selected", generation=1,
            repository="example/disposable", token_file=token_file,
            forbidden_mount=self.checkout)
        self.provider_calls = []

        def run(args, **kwargs):
            if "push" in args:
                self.provider_calls.append(args)
                return subprocess.CompletedProcess(args, 0, b"", b"")
            return subprocess.run(args, **kwargs)

        self.transport = GitHubGitTransport(
            "example/disposable", self.checkout, baseline,
            self.connection.token, run=run)
        self.store = MediationStore(
            self.path / "mediator.sqlite",
            workflow_change_classifier=self.transport.classify_workflow_diff,
            connection_is_current=self.connection.current)

    def _git(self, *args):
        return subprocess.run(["git", "-C", str(self.checkout), *args],
                              check=True, capture_output=True)

    def _grant(self, run: str, branch: str) -> str:
        _, bearer = self.store.issue(
            run_id=run, invocation_id="invocation-" + run,
            repository="example/disposable", branch=branch,
            operations={"git_push"}, ttl_seconds=60,
            connection_id="selected", connection_generation=1)
        return bearer

    def _push(self, bearer: str, branch: str, effect: str):
        return self.store.invoke(
            token=bearer, repository="example/disposable", operation="git_push",
            payload={"branch": branch, "commit": self.commit},
            effect_id=effect, transport=self.transport)

    def test_one_revoked_run_does_not_reach_provider_or_stop_other_run(self):
        a = self._grant("run-a", "branch-a")
        b = self._grant("run-b", "branch-b")
        self.assertEqual(self._push(a, "branch-a", "a-1")["state"], "confirmed")
        self.assertEqual(len(self.provider_calls), 1)
        self.assertEqual(self.store.revoke_run("run-a"), 1)
        with self.assertRaisesRegex(MediationError, "grant_unavailable"):
            self._push(a, "branch-a", "a-2")
        self.assertEqual(len(self.provider_calls), 1)
        self.assertEqual(self._push(b, "branch-b", "b-1")["state"], "confirmed")
        self.assertEqual(len(self.provider_calls), 2)
        self.assertEqual(self._push(b, "branch-b", "b-1")["resent"], False)
        self.assertEqual(len(self.provider_calls), 2)

    def test_connection_replacement_denies_both_old_grants_before_push(self):
        a = self._grant("run-a", "branch-a")
        self.token_file.write_text("GH=synthetic-rotated-token\n", encoding="utf-8")
        with self.assertRaisesRegex(MediationError, "connection_unavailable"):
            self._push(a, "branch-a", "a-1")
        self.assertEqual(self.provider_calls, [])


if __name__ == "__main__":
    unittest.main()
