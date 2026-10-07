"""No-network checks of exact-commit pushes and host-credential isolation."""

from pathlib import Path
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from laomedo.github_git_transport import (GitHubGitTransport,
                                          PushOutcomeUnknown)
from laomedo.github_mediation import KnownRejected
from laomedo import git_credential_helper


REPOSITORY = "example/disposable"


class GitHubGitTransportTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.checkout = Path(self.root.name)
        self._git("init", "-q")
        self._git("config", "user.name", "Test")
        self._git("config", "user.email", "test@example.invalid")
        (self.checkout / "file.txt").write_text("base\n", encoding="utf-8")
        self._git("add", "file.txt")
        self._git("commit", "-qm", "base")
        self.baseline = self._git("rev-parse", "HEAD").stdout.decode().strip()
        (self.checkout / "file.txt").write_text("next\n", encoding="utf-8")
        self._git("commit", "-qam", "next")
        self.commit = self._git("rev-parse", "HEAD").stdout.decode().strip()
        self.push_calls = []

        def runner(args, **kwargs):
            if "push" in args:
                self.push_calls.append((args, kwargs))
                return subprocess.CompletedProcess(args, 0, b"ok", b"")
            return subprocess.run(args, **kwargs)

        self.transport = GitHubGitTransport(
            REPOSITORY, self.checkout, self.baseline,
            lambda connection_id, generation: "synthetic-secret"
            if (connection_id, generation) == ("connection-a", 1) else None,
            run=runner)

    def _git(self, *args):
        return subprocess.run(["git", "-C", str(self.checkout), *args],
                              check=True, capture_output=True)

    def test_exact_commit_push_uses_new_branch_lease_and_no_host_login(self):
        with patch.dict(os.environ, {"GH_TOKEN": "ambient-token",
                                          "GIT_CONFIG_COUNT": "1",
                                          "GCM_TEST": "ambient"}):
            value = self.transport(REPOSITORY, "git_push", {
                "branch": "probe-a", "commit": self.commit},
                connection_id="connection-a", connection_generation=1)
        self.assertEqual(value, {"branch": "probe-a", "commit": self.commit})
        self.assertEqual(len(self.push_calls), 1)
        args, options = self.push_calls[0]
        self.assertIn("--force-with-lease=refs/heads/probe-a:", args)
        self.assertIn(self.commit + ":refs/heads/probe-a", args)
        self.assertIn("https://github.com/example/disposable.git", args)
        self.assertNotIn("synthetic-secret", " ".join(args))
        self.assertNotIn("ambient-token", " ".join(args))
        self.assertNotIn("GH_TOKEN", options["env"])
        self.assertNotIn("GIT_CONFIG_COUNT", options["env"])
        self.assertNotIn("GCM_TEST", options["env"])

    def test_workflow_file_change_is_detected_and_never_pushed(self):
        workflows = self.checkout / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text("name: test\n", encoding="utf-8")
        self._git("add", ".github/workflows/ci.yml")
        self._git("commit", "-qm", "workflow")
        changed = self._git("rev-parse", "HEAD").stdout.decode().strip()
        self.assertTrue(self.transport.classify_workflow_diff(REPOSITORY,
                                                               "probe-a", changed))
        with self.assertRaisesRegex(KnownRejected, "push_commit_unverified"):
            self.transport(REPOSITORY, "git_push", {"branch": "probe-a",
                "commit": changed}, connection_id="connection-a",
                connection_generation=1)
        self.assertEqual(self.push_calls, [])

    def test_replace_ref_cannot_hide_outgoing_workflow(self):
        workflows = self.checkout / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text("name: hidden\n", encoding="utf-8")
        self._git("add", ".github/workflows/ci.yml")
        self._git("commit", "-qm", "real workflow commit")
        real = self._git("rev-parse", "HEAD").stdout.decode().strip()
        self._git("checkout", "-q", self.baseline)
        (self.checkout / "file.txt").write_text("harmless\n", encoding="utf-8")
        self._git("commit", "-qam", "harmless replacement")
        harmless = self._git("rev-parse", "HEAD").stdout.decode().strip()
        self._git("replace", real, harmless)
        # An ordinary checkout diff now sees the replacement, but the
        # isolated staging repository must inspect the real pushed objects.
        ordinary = self._git("diff", "--name-only", self.baseline, real).stdout
        self.assertNotIn(b".github/workflows/", ordinary)
        self.assertTrue(self.transport.classify_workflow_diff(REPOSITORY,
                                                               "probe-a", real))
        with self.assertRaisesRegex(KnownRejected, "push_commit_unverified"):
            self.transport(REPOSITORY, "git_push", {
                "branch": "probe-a", "commit": real},
                connection_id="connection-a", connection_generation=1)
        self.assertEqual(self.push_calls, [])

    def test_missing_or_unbound_commit_is_refused_before_credential(self):
        for commit in ("a" * 40, "HEAD", "", self.baseline[:20]):
            with self.assertRaisesRegex(KnownRejected, "push_commit_unverified"):
                self.transport(REPOSITORY, "git_push", {"branch": "probe-a",
                    "commit": commit}, connection_id="connection-a",
                    connection_generation=1)
        with self.assertRaisesRegex(KnownRejected, "connection_binding_required"):
            self.transport(REPOSITORY, "git_push", {"branch": "probe-a",
                "commit": self.commit})
        with self.assertRaisesRegex(KnownRejected, "push_branch_invalid"):
            self.transport(REPOSITORY, "git_push", {"branch": "../other",
                "commit": self.commit}, connection_id="connection-a",
                connection_generation=1)
        self.assertEqual(self.push_calls, [])

    def test_transport_failure_is_uncertain_not_safe_to_retry(self):
        self.transport.run = lambda args, **kwargs: (
            subprocess.CompletedProcess(
                args, 1, b"synthetic-secret", b"403 synthetic-secret")
            if "push" in args else subprocess.run(args, **kwargs))
        with self.assertRaisesRegex(PushOutcomeUnknown,
                                    "push_outcome_unknown") as found:
            self.transport(REPOSITORY, "git_push", {"branch": "probe-a",
                "commit": self.commit}, connection_id="connection-a",
                connection_generation=1)
        self.assertEqual(found.exception.category,
                         "authentication_or_authorization")
        self.assertEqual(found.exception.exit_code, 1)
        self.assertNotIn("synthetic-secret", str(found.exception))

    def test_git_credential_helper_ignores_host_credentials(self):
        helper = "!" + shlex.quote(sys.executable) + " " + shlex.quote(
            str(Path(git_credential_helper.__file__)))
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(("GIT_CONFIG_", "GCM_")) and
                       key not in {"GH", "GH_TOKEN", "GITHUB_TOKEN"}}
        environment.update({"LAOMEDO_MEDIATED_GIT_TOKEN": "synthetic-only",
                            "GIT_CONFIG_GLOBAL": os.devnull,
                            "GIT_CONFIG_NOSYSTEM": "1",
                            "GIT_TERMINAL_PROMPT": "0"})
        filled = subprocess.run(
            ["git", "-c", "credential.helper=", "-c",
             "credential.helper=" + helper, "credential", "fill"],
            input=b"protocol=https\nhost=github.com\n\n", capture_output=True,
            env=environment, check=False)
        self.assertEqual(filled.returncode, 0)
        self.assertIn(b"password=synthetic-only", filled.stdout)
        refused = subprocess.run(
            ["git", "-c", "credential.helper=", "-c",
             "credential.helper=" + helper, "credential", "fill"],
            input=b"protocol=https\nhost=not-github.invalid\n\n",
            capture_output=True, env=environment, check=False)
        self.assertNotEqual(refused.returncode, 0)
        self.assertNotIn(b"synthetic-only", refused.stdout)


if __name__ == "__main__":
    unittest.main()
