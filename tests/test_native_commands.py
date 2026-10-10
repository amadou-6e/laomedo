"""Development controls, not one-shot campaign evidence or provider parity."""
from pathlib import Path
import base64
import os
import shutil
import subprocess
import tempfile
import unittest
from uuid import uuid4

from laomedo.agent_cli import prepare_commands, configure_remote
from laomedo.github_git_transport import GitHubGitTransport, _base_git_environment
from laomedo.github_mediation import MediationStore, MediationError, KnownRejected
from laomedo.local_runner import _docker_prefix
from laomedo.mediation_authority import RunGrantAuthority, FIRST_SLICE_OPERATIONS


REPO = "example/disposable"
ROOT = Path(__file__).resolve().parents[1]


class NativeCommandsTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("LAOMEDO_TEST_NATIVE_DOCKER") == "1", "opt-in Docker development fixture")
    def test_native_git_and_gh_protocol_in_pinned_image(self):
        from laomedo.local_runner import GIT_IMAGE_ID
        with tempfile.TemporaryDirectory() as temporary:
            wrappers = prepare_commands(Path(temporary), REPO, "run-branch")
            name = "laomedo-native-dev-" + uuid4().hex
            command = ["docker", "run", "--rm", "--name", name,
                "--label=laomedo.native-development=true", "--pull=never", "--network=none", "--read-only",
                "--cap-drop=ALL", "--security-opt=no-new-privileges", "--user=10001:10001",
                "--pids-limit=128", "--memory=1g", "--tmpfs=/tmp:rw,nosuid,size=64m",
                "--env=PATH=/run/laomedo/bin:/usr/local/bin:/usr/bin:/bin",
                "--env=LAOMEDO_REPOSITORY=" + REPO, "--env=LAOMEDO_RUN_BRANCH=run-branch",
                "--env=GIT_CONFIG_NOSYSTEM=1", "--env=GIT_CONFIG_GLOBAL=/dev/null"]
            for source, target in ((wrappers, "/run/laomedo/bin"),
                (ROOT / "laomedo/agent_gh_adapter.mjs", "/run/laomedo/gh.mjs"),
                (ROOT / "laomedo/agent_git_remote.mjs", "/run/laomedo/git-remote.mjs"),
                (ROOT / "tests/fixtures/native_mediation_stub.mjs", "/run/laomedo/mediate.mjs"),
                (ROOT / "tests/fixtures/native_command_fixture.mjs", "/run/laomedo/test.mjs")):
                command.extend(["--mount", f"type=bind,source={source},target={target},readonly"])
            command.extend([GIT_IMAGE_ID, "node", "/run/laomedo/test.mjs"])
            try:
                result = subprocess.run(command, capture_output=True, timeout=60)
            finally:
                inspected = subprocess.run(["docker", "inspect", name, "--format",
                    '{{index .Config.Labels "laomedo.native-development"}}'], capture_output=True, timeout=10)
                if inspected.returncode == 0:
                    self.assertEqual(inspected.stdout.strip(), b"true")
                    subprocess.run(["docker", "rm", "-f", name], check=True, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertIn(b'"native_fetch":true', result.stdout)

    def test_wrappers_and_mounts_are_agent_only_and_readonly(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wrappers = prepare_commands(root, REPO, "run-branch")
            self.assertNotIn(b"\r", (wrappers / "gh").read_bytes())
            command = _docker_prefix(root, root, root, capability=root / "capability",
                mediator_url="http://host.docker.internal:1234/v1/mediate",
                mediator_instance="a" * 32, command_directory=wrappers,
                repository=REPO, branch="run-branch")
            self.assertIn("LAOMEDO_REPOSITORY=" + REPO, command)
            self.assertIn("LAOMEDO_RUN_BRANCH=run-branch", command)
            self.assertIn(f"type=bind,source={wrappers},target=/run/laomedo/bin,readonly", command)
            self.assertNotIn("GH_TOKEN", " ".join(command))
            self.assertTrue((ROOT / "laomedo/agent_gh_adapter.mjs").is_file())
            self.assertTrue((ROOT / "laomedo/agent_git_remote.mjs").is_file())
            self.assertEqual(prepare_commands(root, REPO, "run-branch"), wrappers)
            (wrappers / "gh").write_text("modified", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "command_wrapper_changed"):
                prepare_commands(root, REPO, "run-branch")

    @unittest.skipUnless(shutil.which("node"), "Node unavailable")
    def test_production_gh_adapter_controls(self):
        result = subprocess.run(["node", "--test", "tests/test_agent_gh.mjs"], cwd=ROOT,
            capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertIn(b"# pass 18", result.stdout)

    @unittest.skipUnless(shutil.which("git"), "Git unavailable")
    def test_remote_setup_is_idempotent_and_refuses_changed_url(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "-C", str(root), "init", "--quiet"], check=True)
            configure_remote(root, REPO)
            configure_remote(root, REPO)
            (root / ".laomedo-handoff.bundle").write_bytes(b"fixture bundle")
            status = subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                check=True, capture_output=True).stdout
            self.assertNotIn(b".laomedo-handoff.bundle", status)
            subprocess.run(["git", "-C", str(root), "remote", "set-url", "origin", "https://other.invalid"], check=True)
            with self.assertRaisesRegex(ValueError, "mediated_remote_changed"):
                configure_remote(root, REPO)

    def test_fetch_approval_carries_trusted_base_and_preserves_old_permissions(self):
        with tempfile.TemporaryDirectory() as temporary:
            authority = RunGrantAuthority(Path(temporary) / "authority.sqlite")
            ref = authority.approve(invocation_id="invocation", repository=REPO, branch="run-branch",
                base_branch="develop", operations={"git_fetch"}, reviewed_by="operator")
            scope = authority.bind_run(ref, "run", allowed_operations=FIRST_SLICE_OPERATIONS)
            self.assertEqual(scope["base_branch"], "develop")
            lease = {"run_id": "run", "token": "lease"}
            altered = {**scope, "base_branch": "other"}
            self.assertIsNone(authority.authorize_lease(lease, altered))
            approved = authority.authorize_lease(lease, scope)
            self.assertEqual(approved["operations"], {"git_fetch"})
            self.assertEqual(approved["base_branch"], "develop")
            old = authority.approve(invocation_id="old", repository=REPO, branch="old-branch",
                operations={"actions_read"}, reviewed_by="operator")
            authority.bind_run(old, "old-run")
            old_scope = {"invocation_id": "old", "repository": REPO, "branch": "old-branch"}
            self.assertEqual(authority.authorize_lease({"run_id": "old-run", "token": "old-lease"},
                old_scope)["operations"], {"actions_read"})

    def test_fetch_scope_uses_configured_base_not_hardcoded_main(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = MediationStore(Path(temporary) / "store.sqlite")
            _, token = store.issue(run_id="run", invocation_id="invocation", repository=REPO,
                branch="run-branch", base_branch="develop", operations={"git_fetch"}, ttl_seconds=60)
            calls = []
            def provider(*args):
                calls.append(args)
                return {"fixture": True}
            for branch in ("develop", "run-branch"):
                result = store.invoke(token=token, repository=REPO, operation="git_fetch",
                    payload={"action": "fetch", "ref": "refs/heads/" + branch, "commit": "a" * 40},
                    effect_id=None, transport=provider)
                self.assertEqual(result["state"], "confirmed")
            with self.assertRaises(MediationError) as found:
                store.invoke(token=token, repository=REPO, operation="git_fetch",
                    payload={"action": "fetch", "ref": "refs/heads/main", "commit": "a" * 40},
                    effect_id=None, transport=provider)
            self.assertEqual(found.exception.code, "fetch_target_denied")
            self.assertEqual(len(calls), 2)

    def test_push_predecessor_is_taken_from_confirmed_journal_not_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = MediationStore(Path(temporary) / "store.sqlite",
                connection_is_current=lambda *_args: True,
                workflow_change_classifier=lambda *_args: False)
            _, token = store.issue(run_id="run", invocation_id="invocation", repository=REPO,
                branch="run-branch", operations={"git_push"}, ttl_seconds=60,
                connection_id="connection", connection_generation=1)
            calls = []
            def provider(repo, op, payload, **binding):
                calls.append(binding)
                return {"branch": payload["branch"], "commit": payload["commit"]}
            for index, commit in enumerate(("a" * 40, "b" * 40)):
                result = store.invoke(token=token, repository=REPO, operation="git_push",
                    payload={"branch": "run-branch", "commit": commit}, effect_id=f"effect-{index}",
                    transport=provider)
                self.assertEqual(result["state"], "confirmed")
            self.assertNotIn("expected_remote_commit", calls[0])
            self.assertEqual(calls[1]["expected_remote_commit"], "a" * 40)
            # Unknown predecessor effects still fence all fresh identities.
            def uncertain(*args, **kwargs):
                raise TimeoutError("synthetic")
            self.assertEqual(store.invoke(token=token, repository=REPO, operation="git_push",
                payload={"branch": "run-branch", "commit": "c" * 40}, effect_id="unknown",
                transport=uncertain)["state"], "unknown")
            with self.assertRaises(MediationError) as found:
                store.invoke(token=token, repository=REPO, operation="git_push",
                    payload={"branch": "run-branch", "commit": "d" * 40}, effect_id="fresh",
                    transport=provider)
            self.assertEqual(found.exception.code, "prior_effect_unknown")
            self.assertEqual(len(calls), 2)

    @unittest.skipUnless(shutil.which("git"), "Git unavailable")
    def test_host_fetch_objects_and_exact_scope_without_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "source"
            repository.mkdir()
            def git(*args):
                return subprocess.run(["git", "-C", str(repository), *args],
                    capture_output=True, check=True, env=_base_git_environment()).stdout.decode().strip()
            git("init", "--quiet", "-b", "main")
            (repository / "file").write_text("fixture", encoding="ascii")
            git("add", "file")
            git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                "commit", "--quiet", "-m", "fixture")
            commit = git("rev-parse", "HEAD")
            calls = []
            def provider(args, **options):
                rewritten = [str(repository) if value == "https://github.com/" + REPO + ".git"
                             else value for value in args]
                if "ls-remote" in args or "fetch" in args:
                    calls.append(args)
                    self.assertEqual(options["env"].get("LAOMEDO_MEDIATED_GIT_TOKEN"), "synthetic")
                    self.assertNotIn("GH_TOKEN", options["env"])
                return subprocess.run(rewritten, **options)
            transport = GitHubGitTransport(REPO, repository, commit,
                lambda cid, gen: "synthetic", run=provider)
            binding = {"connection_id": "connection", "connection_generation": 1, "allowed_branch": "run-branch"}
            listing = transport(REPO, "git_fetch", {"action": "list"}, **binding)
            self.assertEqual(listing, {"refs": [{"ref": "refs/heads/main", "commit": commit}]})
            result = transport(REPO, "git_fetch", {"action": "fetch", "ref": "refs/heads/main", "commit": commit}, **binding)
            bundle = root / "read.bundle"
            bundle.write_bytes(base64.b64decode(result["bundle"]))
            self.assertLessEqual(bundle.stat().st_size, 262144)
            self.assertEqual(git("bundle", "list-heads", str(bundle)), commit + " refs/heads/laomedo-read")
            count = len(calls)
            with self.assertRaises(KnownRejected):
                transport(REPO, "git_fetch", {"action": "fetch", "ref": "refs/heads/other", "commit": commit}, **binding)
            self.assertEqual(count, len(calls))
            with self.assertRaisesRegex(KnownRejected, "fetch_ref_changed"):
                transport(REPO, "git_fetch", {"action": "fetch", "ref": "refs/heads/main", "commit": "0" * 40}, **binding)

    def test_fetch_rechecks_grant_before_delivering_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = MediationStore(Path(temporary) / "store.sqlite")
            gid, token = store.issue(run_id="run", invocation_id="invocation", repository=REPO,
                branch="run-branch", operations={"git_fetch"}, ttl_seconds=60)
            def provider(*args):
                store.revoke_run("run")
                return {"refs": []}
            with self.assertRaises(MediationError) as found:
                store.invoke(token=token, repository=REPO, operation="git_fetch", payload={"action": "list"},
                    effect_id=None, transport=provider)
            self.assertEqual(found.exception.code, "grant_unavailable")

    @unittest.skipUnless(shutil.which("node"), "Node unavailable")
    def test_remote_helper_target_and_push_batch_controls(self):
        script = """
import { target, pushTarget } from './laomedo/agent_git_remote.mjs';
import assert from 'node:assert/strict';
const context = {repository:'example/disposable', branch:'run-branch'};
target('laomedo::example/disposable', context);
assert.throws(() => target('https://github.com/example/disposable.git', context));
assert.deepEqual(pushTarget(['push HEAD:refs/heads/run-branch'], context.branch), ['HEAD','refs/heads/run-branch']);
for (const batch of [['push +HEAD:refs/heads/run-branch'], ['push HEAD:refs/heads/other'],
 ['push :refs/heads/run-branch'], ['push HEAD:refs/heads/run-branch', 'push HEAD:refs/heads/other']]) {
 assert.throws(() => pushTarget(batch, context.branch));
}
"""
        result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=ROOT,
            capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr.decode())


if __name__ == "__main__":
    unittest.main()
