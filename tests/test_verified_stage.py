"""Credential-free local checks for a grant-bound verified bundle snapshot."""

import hashlib
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from laomedo.bundle_ingest import HANDOFF_NAME, freeze_run_bundle, _record
from laomedo.bundle_stage import PINNED_IMAGE_ID
from laomedo.verified_stage import VerifiedStageError, resolve_verified_stage
from laomedo.verified_git_stage import (VerifiedGitStageError,
                                        stage_verified_git)
from laomedo.github_git_transport import _run_bounded_tree
from laomedo.github_git_transport import GitHubGitTransport
from laomedo.github_mediation import MediationStore, MediationError, KnownRejected
from laomedo.verified_git_stage import (make_grant_stage_resolver,
                                        make_grant_bundle_freezer,
                                        classify_verified_workflow)


class VerifiedStageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "source"
        self.repo.mkdir()
        self.git("init", "--quiet")
        (self.repo / "base").write_text("base", encoding="ascii")
        self.git("add", "base")
        self.git("-c", "user.name=Test", "-c", "user.email=t@example.invalid",
                 "commit", "--quiet", "-m", "base")
        self.baseline = self.git("rev-parse", "HEAD")
        (self.repo / "change").write_text("change", encoding="ascii")
        self.git("add", "change")
        self.git("-c", "user.name=Test", "-c", "user.email=t@example.invalid",
                 "commit", "--quiet", "-m", "change")
        self.commit = self.git("rev-parse", "HEAD")
        self.git("branch", "run-branch", self.commit)
        self.git("branch", "validated", self.commit)
        self.runner = self.root / "runner"
        self.private = self.root / "private"
        self.workspace = self.runner / "runs" / "run-a" / "workspace"
        self.workspace.mkdir(parents=True)
        self.private.mkdir()
        self.record = self.workspace.parent / "record.json"
        self.record.write_text(json.dumps({
            "run_id": "run-a", "status": "completed", "workspace_mode": "git",
            "git_baseline": self.baseline,
            "github_scope": {"repository": "example/disposable",
                             "branch": "run-branch"}}), encoding="utf-8")
        self.git("bundle", "create", str(self.workspace / HANDOFF_NAME),
                 "refs/heads/run-branch")
        frozen = freeze_run_bundle(self.runner, self.private, run_id="run-a",
                                   attempt_id="attempt-1")
        self.assertEqual(frozen["status"], "frozen")
        self.attempt = self.private / "run-a" / "attempt-1"
        self.verified = self.attempt / "verified.bundle"
        self.git("bundle", "create", str(self.verified), "refs/heads/validated")
        self.verification = self.attempt / "verification.json"
        self.verification.write_text(json.dumps({
            "run_id": "run-a", "attempt_id": "attempt-1",
            "status": "verified", "source_bundle_sha256": frozen["bundle_sha256"],
            "baseline": self.baseline, "commit": self.commit,
            "image_id": PINNED_IMAGE_ID,
            "baseline_bundle_sha256": "a" * 64,
            "policy_approved": False,
            "container": {"status": "verified", "cleanup_verified": True,
                          "success_marker_seen": True, "limits_verified": True,
                          "export_class": "ok",
                          "output_sha256": hashlib.sha256(
                              self.verified.read_bytes()).hexdigest(),
                          "output_bytes": self.verified.stat().st_size}}),
            encoding="utf-8")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                              capture_output=True).stdout.decode().strip()

    def resolve(self, **overrides):
        scope = {"run_id": "run-a", "repository": "example/disposable",
                 "branch": "run-branch", "commit": self.commit,
                 "stage_attempt_id": "attempt-1"}
        scope.update(overrides)
        return resolve_verified_stage(self.runner, self.private, **scope)

    def test_verified_snapshot_is_immutable_and_pathless(self):
        stage = self.resolve()
        original = stage.bundle
        self.verified.write_bytes(b"tampered")
        self.assertEqual(stage.bundle, original)
        self.assertEqual(stage.bundle_sha256, hashlib.sha256(original).hexdigest())
        self.assertNotIn(str(self.private), repr(stage))
        self.assertNotIn(repr(original), repr(stage))
        with self.assertRaises(VerifiedStageError):
            self.resolve()

    def progression_store(self, *, unknown=False, confirm=True):
        store = MediationStore(self.root / "effects.sqlite",
            verified_stage_resolver=make_grant_stage_resolver(self.runner, self.private, self.runner),
            verified_workflow_classifier=classify_verified_workflow)
        gid, token = store.issue(run_id="run-a", invocation_id="inv-a", repository="example/disposable",
            branch="run-branch", operations={"git_push"}, ttl_seconds=60)
        record = json.loads(self.record.read_bytes())
        record.update(status="running", container_ownership={"name": "owned-a", "launch_token": "launch-a",
            "grant_id": gid, "supervised": True, "cleanup_verified": False})
        self.record.write_text(json.dumps(record), encoding="utf-8")
        # Synthetic existing stage: change its binding to the live fixture.
        manifest = self.attempt / "result.json"
        frozen = json.loads(manifest.read_bytes())
        frozen.update(_record(self.runner, "run-a")[1])
        frozen.pop("run_record_sha256", None)
        manifest.write_text(json.dumps(frozen), encoding="utf-8")
        store.stage_freezer = make_grant_bundle_freezer(self.runner, self.private, self.runner,
            confirmed_stage_authorizer=store.confirmed_stage)
        def transport(*args, **kwargs):
            if unknown:
                raise TimeoutError("synthetic")
            return {"branch": "run-branch", "commit": self.commit}
        if confirm:
            store.invoke(token=token, repository="example/disposable", operation="git_push",
                payload={"branch": "run-branch", "commit": self.commit, "stage_attempt_id": "attempt-1"},
                effect_id="first", transport=transport)
        return store, token

    def next_capture(self, store, token):
        return store.invoke(token=token, repository="example/disposable", operation="bundle_freeze",
            payload={"attempt_id": "attempt-2"}, effect_id=None,
            transport=lambda *_args: self.fail("freeze must not contact provider"))

    def test_confirmed_clean_same_grant_stage_allows_next_capture(self):
        store, token = self.progression_store()
        self.assertEqual(self.next_capture(store, token)["state"], "confirmed")
        self.assertTrue((self.private / "run-a/attempt-2/input.bundle").is_file())

    def test_verified_but_unconfirmed_stage_does_not_allow_next_capture(self):
        store, token = self.progression_store(confirm=False)
        self.assertEqual(self.next_capture(store, token)["state"], "unknown")
        self.assertFalse((self.private / "run-a/attempt-2").exists())

    def test_unknown_push_blocks_next_capture_before_reservation(self):
        store, token = self.progression_store(unknown=True)
        with self.assertRaisesRegex(MediationError, "prior_effect_unknown"):
            self.next_capture(store, token)
        self.assertFalse((self.private / "run-a/attempt-2").exists())

    def test_changed_verified_bytes_block_next_capture(self):
        store, token = self.progression_store()
        self.verified.write_bytes(b"changed")
        self.assertEqual(self.next_capture(store, token)["state"], "unknown")
        self.assertFalse((self.private / "run-a/attempt-2").exists())

    def test_unclean_verified_stage_blocks_next_capture(self):
        store, token = self.progression_store()
        value = json.loads(self.verification.read_bytes())
        value["container"]["cleanup_verified"] = False
        self.verification.write_text(json.dumps(value), encoding="utf-8")
        self.assertEqual(self.next_capture(store, token)["state"], "unknown")
        self.assertFalse((self.private / "run-a/attempt-2").exists())

    def test_changed_live_grant_blocks_next_capture(self):
        store, token = self.progression_store()
        value = json.loads(self.record.read_bytes())
        value["container_ownership"]["grant_id"] = "other-grant"
        self.record.write_text(json.dumps(value), encoding="utf-8")
        self.assertEqual(self.next_capture(store, token)["state"], "unknown")
        self.assertFalse((self.private / "run-a/attempt-2").exists())

    def test_wrong_grant_scope_or_commit_refuses(self):
        for scope in ({"run_id": "run-b"}, {"repository": "other/disposable"},
                      {"branch": "other"}, {"commit": "0" * 40},
                      {"stage_attempt_id": "other"}):
            with self.subTest(scope=scope), self.assertRaises(VerifiedStageError):
                self.resolve(**scope)

    def test_live_stage_tracks_stable_grant_and_refuses_after_completion(self):
        live_workspace = self.runner / "runs" / "run-live" / "workspace"
        live_workspace.mkdir(parents=True)
        live_record = live_workspace.parent / "record.json"
        owner = {"name": "laomedo-codex-live", "launch_token": "launch-live",
                 "grant_id": "grant-live", "supervised": True,
                 "cleanup_verified": False}
        record = {"run_id": "run-live", "status": "running",
                  "workspace_mode": "git", "git_baseline": self.baseline,
                  "github_scope": {"repository": "example/disposable",
                                   "branch": "run-branch"},
                  "container_ownership": owner}
        live_record.write_text(json.dumps(record), encoding="utf-8")
        (live_workspace / HANDOFF_NAME).write_bytes(
            (self.workspace / HANDOFF_NAME).read_bytes())
        frozen = freeze_run_bundle(self.runner, self.private, run_id="run-live",
                                   attempt_id="attempt-live")
        attempt = self.private / "run-live" / "attempt-live"
        (attempt / "verified.bundle").write_bytes(self.verified.read_bytes())
        verification = json.loads(self.verification.read_text())
        verification.update(run_id="run-live", attempt_id="attempt-live",
                            source_bundle_sha256=frozen["bundle_sha256"])
        (attempt / "verification.json").write_text(json.dumps(verification),
                                                     encoding="utf-8")
        scope = {"run_id": "run-live", "repository": "example/disposable",
                 "branch": "run-branch", "commit": self.commit,
                 "stage_attempt_id": "attempt-live",
                 "expected_grant_id": "grant-live"}
        first = resolve_verified_stage(self.runner, self.private, **scope)
        record["thread_id"] = "native-thread"
        record["turns"] = [{"status": "running"}]
        live_record.write_text(json.dumps(record), encoding="utf-8")
        self.assertEqual(resolve_verified_stage(self.runner, self.private,
                                                **scope).stage_digest,
                         first.stage_digest)
        with self.assertRaisesRegex(VerifiedStageError, "stage_grant_mismatch"):
            resolve_verified_stage(self.runner, self.private,
                                   **{**scope, "expected_grant_id": "grant-other"})
        owner["grant_id"] = "grant-other"
        live_record.write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaises(VerifiedStageError):
            resolve_verified_stage(self.runner, self.private, **scope)
        owner["grant_id"] = "grant-live"
        record["status"] = "completed"
        live_record.write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaises(VerifiedStageError):
            resolve_verified_stage(self.runner, self.private, **scope)

    def test_agent_freeze_uses_only_active_grant_and_fixed_handoff(self):
        workspace = self.runner / "runs" / "run-freeze" / "workspace"
        workspace.mkdir(parents=True)
        (workspace / HANDOFF_NAME).write_bytes(
            (self.workspace / HANDOFF_NAME).read_bytes())
        store = MediationStore(self.root / "freeze-effects.sqlite",
            stage_freezer=make_grant_bundle_freezer(
                self.runner, self.private, self.root / "agent-mount"))
        grant_id, token = store.issue(run_id="run-freeze",
            invocation_id="invocation-freeze", repository="example/disposable",
            branch="run-branch", operations={"git_push"}, ttl_seconds=60)
        record_path = workspace.parent / "record.json"
        record = {"run_id": "run-freeze", "status": "running",
                  "workspace_mode": "git", "git_baseline": self.baseline,
                  "github_scope": {"repository": "example/disposable",
                                   "branch": "run-branch"},
                  "container_ownership": {
                      "name": "laomedo-codex-freeze", "launch_token": "launch-freeze",
                      "grant_id": grant_id, "supervised": True,
                      "cleanup_verified": False}}
        record_path.write_text(json.dumps(record), encoding="utf-8")
        provider_calls = []
        def invoke(payload, supplied=token):
            return store.invoke(token=supplied, repository="example/disposable",
                operation="bundle_freeze", payload=payload, effect_id=None,
                transport=lambda *_args: provider_calls.append(1))
        with self.assertRaisesRegex(MediationError, "freeze_request_invalid"):
            invoke({"attempt_id": "attempt-a", "path": str(self.repo)})
        result = invoke({"attempt_id": "attempt-a"})
        self.assertEqual(result["state"], "confirmed")
        self.assertEqual(result["result"]["status"], "frozen")
        self.assertEqual(result["result"]["grant_id"], grant_id)
        self.assertEqual(provider_calls, [])
        self.assertEqual(invoke({"attempt_id": "attempt-a"})["state"], "unknown")
        store.revoke_run("run-freeze")
        with self.assertRaisesRegex(MediationError, "grant_unavailable"):
            invoke({"attempt_id": "attempt-b"})
        self.assertFalse((self.private / "run-freeze" / "attempt-b").exists())

    def test_changed_record_or_frozen_source_refuses(self):
        original = self.record.read_bytes()
        self.record.write_bytes(original + b" ")
        with self.assertRaises(VerifiedStageError):
            self.resolve()
        self.record.write_bytes(original)
        (self.attempt / "input.bundle").write_bytes(b"tampered")
        with self.assertRaises(VerifiedStageError):
            self.resolve()

    def test_unverified_or_unclean_attempt_refuses(self):
        for section, key, value in (("top", "status", "unknown"),
                                    ("top", "run_id", "run-b"),
                                    ("top", "attempt_id", "attempt-2"),
                                    ("top", "policy_approved", True),
                                    ("top", "image_id", "sha256:" + "0" * 64),
                                    ("top", "baseline_bundle_sha256", "bad"),
                                    ("container", "cleanup_verified", False),
                                    ("container", "success_marker_seen", False),
                                    ("container", "limits_verified", False),
                                    ("container", "export_class", "failed"),
                                    ("container", "output_bytes", 0),
                                    ("container", "output_sha256", "0" * 64),
                                    ("top", "source_bundle_sha256", "0" * 64)):
            original = self.verification.read_bytes()
            record = json.loads(original)
            target = record if section == "top" else record["container"]
            target[key] = value
            self.verification.write_text(json.dumps(record), encoding="utf-8")
            with self.subTest(key=key), self.assertRaises(VerifiedStageError):
                self.resolve()
            self.verification.write_bytes(original)

    def test_linked_or_oversized_output_refuses(self):
        linked = self.root / "linked.bundle"
        os.link(self.verified, linked)
        with self.assertRaises(VerifiedStageError):
            self.resolve()
        linked.unlink()
        self.verified.write_bytes(b"x" * (32 * 1024 * 1024 + 1))
        with self.assertRaises(VerifiedStageError):
            self.resolve()

    def test_symlinked_stage_files_refuse(self):
        for target in (self.verification, self.verified):
            original = target.read_bytes()
            other = self.root / "other-file"
            other.write_bytes(original)
            target.unlink()
            try:
                target.symlink_to(other)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation is unavailable")
            with self.assertRaises(VerifiedStageError):
                self.resolve()
            target.unlink()
            target.write_bytes(original)
            other.unlink()

    def test_real_second_run_cannot_be_reached_by_first_run_scope(self):
        other = self.runner / "runs" / "run-b"
        (other / "workspace").mkdir(parents=True)
        record = json.loads(self.record.read_text())
        record["run_id"] = "run-b"
        (other / "record.json").write_text(json.dumps(record))
        second_home = self.private / "run-b" / "exclusive-b"
        second_home.mkdir(parents=True)
        frozen = json.loads((self.attempt / "result.json").read_text())
        frozen["run_id"] = "run-b"
        frozen["attempt_id"] = "exclusive-b"
        frozen["run_record_sha256"] = hashlib.sha256(
            (other / "record.json").read_bytes()).hexdigest()
        (second_home / "result.json").write_text(json.dumps(frozen))
        (second_home / "input.bundle").write_bytes(
            (self.attempt / "input.bundle").read_bytes())
        (second_home / "verified.bundle").write_bytes(self.verified.read_bytes())
        verification = json.loads(self.verification.read_text())
        verification.update(run_id="run-b", attempt_id="exclusive-b")
        (second_home / "verification.json").write_text(json.dumps(verification))
        other_stage = self.resolve(run_id="run-b", stage_attempt_id="exclusive-b")
        self.assertEqual(other_stage.run_id, "run-b")
        # The first run grant cannot reach the other run's unique attempt.
        with self.assertRaises(VerifiedStageError):
            self.resolve(stage_attempt_id="exclusive-b")

    def test_distinct_attempt_changes_stage_digest(self):
        first = self.resolve()
        second_attempt = self.private / "run-a" / "attempt-2"
        second_attempt.mkdir()
        frozen = json.loads((self.attempt / "result.json").read_text())
        frozen["attempt_id"] = "attempt-2"
        (second_attempt / "result.json").write_text(json.dumps(frozen))
        (second_attempt / "input.bundle").write_bytes(
            (self.attempt / "input.bundle").read_bytes())
        (second_attempt / "verified.bundle").write_bytes(self.verified.read_bytes())
        verification = json.loads(self.verification.read_text())
        verification["attempt_id"] = "attempt-2"
        (second_attempt / "verification.json").write_text(json.dumps(verification))
        second = self.resolve(stage_attempt_id="attempt-2")
        self.assertNotEqual(first.stage_digest, second.stage_digest)
        self.assertEqual(first.bundle_sha256, second.bundle_sha256)

    def test_snapshot_is_the_only_git_object_source(self):
        snapshot = self.resolve()
        self.verified.write_bytes(b"changed on host after resolution")
        (self.repo / "change").write_text("changed by agent", encoding="ascii")
        with stage_verified_git(snapshot) as staged:
            self.assertFalse(staged.classify_workflow_change())
            self.assertEqual(staged.git("rev-parse", "refs/stage/validated").stdout.strip(),
                             snapshot.commit.encode())
            self.assertEqual(staged.git("cat-file", "-t", snapshot.commit).stdout.strip(),
                             b"commit")
            self.assertTrue(staged.bare.is_dir())
        self.assertFalse(staged.bare.exists())

    def test_connectivity_check_rejects_a_broken_anchored_ref(self):
        snapshot = self.resolve()
        def inject_broken_ref(args, **options):
            if "fsck" in args:
                bare = Path(args[args.index("-C") + 1])
                broken = bare / "refs" / "stage" / "broken"
                broken.parent.mkdir(parents=True, exist_ok=True)
                broken.write_text("0" * 40 + "\n", encoding="ascii")
            return _run_bounded_tree(args, **options)
        with self.assertRaises(VerifiedGitStageError):
            with stage_verified_git(snapshot, run=inject_broken_ref):
                pass

    def test_workflow_change_and_missing_baseline_are_distinguished(self):
        snapshot = self.resolve()
        workflow = self.repo / ".github" / "workflows" / "test.yml"
        workflow.parent.mkdir(parents=True)
        workflow.write_text("name: test\n", encoding="ascii")
        self.git("add", ".github/workflows/test.yml")
        self.git("-c", "user.name=Test", "-c", "user.email=t@example.invalid",
                 "commit", "--quiet", "-m", "workflow")
        changed_commit = self.git("rev-parse", "HEAD")
        self.git("branch", "-f", "validated", changed_commit)
        changed_bundle = self.root / "changed.bundle"
        self.git("bundle", "create", str(changed_bundle), "refs/heads/validated")
        payload = changed_bundle.read_bytes()
        changed = replace(snapshot, commit=changed_commit, bundle=payload,
                          bundle_sha256=hashlib.sha256(payload).hexdigest())
        with stage_verified_git(changed) as staged:
            self.assertTrue(staged.classify_workflow_change())
        with stage_verified_git(replace(snapshot, baseline="0" * 40)) as staged:
            with self.assertRaises(VerifiedGitStageError):
                staged.classify_workflow_change()

    def test_bad_bundle_identity_or_integrity_refuses(self):
        snapshot = self.resolve()
        invalid = [
            replace(snapshot, commit="0" * 40),
            replace(snapshot, bundle=snapshot.bundle + b"tamper"),
            replace(snapshot, bundle=snapshot.bundle[:-20],
                    bundle_sha256=hashlib.sha256(
                        snapshot.bundle[:-20]).hexdigest()),
        ]
        alternate = snapshot.bundle.replace(b"refs/heads/validated",
                                            b"refs/heads/untrusted", 1)
        invalid.append(replace(snapshot, bundle=alternate,
                               bundle_sha256=hashlib.sha256(alternate).hexdigest()))
        for changed in invalid:
            with self.subTest(commit=changed.commit,
                              length=len(changed.bundle)), self.assertRaises(
                                  VerifiedGitStageError):
                with stage_verified_git(changed):
                    pass

    def mediator(self, *, run_id="run-a", classifier=classify_verified_workflow):
        store = MediationStore(
            self.root / "effects.sqlite",
            verified_stage_resolver=make_grant_stage_resolver(
                self.runner, self.private, self.root / "agent-mount"),
            verified_workflow_classifier=classifier)
        grant_id, token = store.issue(run_id=run_id, invocation_id="invocation-a",
            repository="example/disposable", branch="run-branch",
            operations={"git_push"}, ttl_seconds=60)
        if run_id == "run-a":
            record = json.loads(self.record.read_text())
            record.update(status="running", container_ownership={
                "name": "laomedo-codex-a", "launch_token": "launch-a",
                "grant_id": grant_id, "supervised": True,
                "cleanup_verified": False})
            self.record.write_text(json.dumps(record), encoding="utf-8")
            from laomedo.bundle_ingest import _record
            binding = _record(self.runner, "run-a")[1]
            frozen = json.loads((self.attempt / "result.json").read_text())
            frozen.pop("run_record_sha256")
            frozen.update(binding)
            (self.attempt / "result.json").write_text(json.dumps(frozen),
                                                       encoding="utf-8")
        return store, token

    def test_mediator_refuses_completed_run_even_with_unexpired_grant(self):
        store, token = self.mediator()
        record = json.loads(self.record.read_text())
        record["status"] = "completed"
        self.record.write_text(json.dumps(record), encoding="utf-8")
        calls = []
        with self.assertRaisesRegex(MediationError, "push_stage_unverified"):
            store.invoke(token=token, repository="example/disposable",
                operation="git_push", payload={"branch": "run-branch",
                    "commit": self.commit, "stage_attempt_id": "attempt-1"},
                effect_id="effect-after-completion",
                transport=lambda *_args, **_kwargs: calls.append(1))
        self.assertEqual(calls, [])

    def test_mediator_binds_snapshot_digest_and_never_redispatches(self):
        store, token = self.mediator()
        calls = []
        payload = {"branch": "run-branch", "commit": self.commit,
                   "stage_attempt_id": "attempt-1"}
        def transport(repository, operation, outgoing, *, verified_stage):
            calls.append((repository, operation, verified_stage.stage_digest))
            self.verified.write_bytes(b"changed after preflight")
            self.assertEqual(verified_stage.bundle_sha256, hashlib.sha256(
                verified_stage.bundle).hexdigest())
            return {"stage_digest": verified_stage.stage_digest}
        result = store.invoke(token=token, repository="example/disposable",
            operation="git_push", payload=payload, effect_id="effect-a",
            transport=transport)
        self.assertEqual(result["state"], "confirmed")
        self.assertEqual(len(calls), 1)
        effect = store.effect("run-a", "effect-a")
        self.assertEqual(effect["state"], "confirmed")
        # An exact repeat returns the saved outcome without rereading a
        # changed/removed stage or sending a second provider request.
        repeated = store.invoke(token=token, repository="example/disposable",
            operation="git_push", payload=payload, effect_id="effect-a",
            transport=transport)
        self.assertEqual(repeated["state"], "confirmed")
        with self.assertRaisesRegex(MediationError, "effect_conflict"):
            store.invoke(token=token, repository="example/disposable",
                operation="git_push",
                payload={**payload, "stage_attempt_id": "attempt-2"},
                effect_id="effect-a", transport=transport)
        self.assertEqual(len(calls), 1)

    def test_wrong_grant_or_workflow_change_never_journals_push(self):
        payload = {"branch": "run-branch", "commit": self.commit,
                   "stage_attempt_id": "attempt-1"}
        for run, classifier in (("run-b", classify_verified_workflow),
                                ("run-a", lambda _stage: True)):
            with self.subTest(run=run, classifier=classifier):
                if (self.root / "effects.sqlite").exists():
                    (self.root / "effects.sqlite").unlink()
                store, token = self.mediator(run_id=run, classifier=classifier)
                calls = []
                with self.assertRaises(MediationError):
                    store.invoke(token=token, repository="example/disposable",
                        operation="git_push", payload=payload, effect_id="effect-a",
                        transport=lambda *_args, **_kwargs: calls.append(1))
                self.assertEqual(calls, [])
                self.assertIsNone(store.effect(run, "effect-a"))

    def test_configured_transport_cannot_fallback_to_checkout(self):
        supplied = []
        transport = GitHubGitTransport("example/disposable", self.repo,
            self.baseline, lambda *_args: supplied.append(1) or "unused",
            require_verified_stage=True)
        with self.assertRaisesRegex(KnownRejected, "push_stage_required"):
            transport("example/disposable", "git_push",
                {"branch": "run-branch", "commit": self.commit},
                connection_id="connection-a", connection_generation=1)
        self.assertEqual(supplied, [])

    def test_unknown_staged_push_blocks_new_effect_on_same_branch(self):
        store, token = self.mediator()
        payload = {"branch": "run-branch", "commit": self.commit,
                   "stage_attempt_id": "attempt-1"}
        calls = []
        def uncertain(_repository, _operation, _payload, *, verified_stage):
            calls.append(verified_stage.stage_digest)
            raise RuntimeError("synthetic lost reply")
        first = store.invoke(token=token, repository="example/disposable",
            operation="git_push", payload=payload, effect_id="effect-a",
            transport=uncertain)
        self.assertEqual(first["state"], "unknown")
        self.assertEqual(store.invoke(token=token, repository="example/disposable",
            operation="git_push", payload=payload, effect_id="effect-a",
            transport=uncertain), {"state": "unknown", "resent": False})
        with self.assertRaisesRegex(MediationError, "prior_effect_unknown"):
            store.invoke(token=token, repository="example/disposable",
                operation="git_push", payload=payload, effect_id="effect-b",
                transport=uncertain)
        self.assertEqual(len(calls), 1)

    def test_transport_rechecks_real_workflow_diff_before_credential(self):
        snapshot = self.resolve()
        workflow = self.repo / ".github" / "workflows" / "test.yml"
        workflow.parent.mkdir(parents=True)
        workflow.write_text("name: test\n", encoding="ascii")
        self.git("add", ".github/workflows/test.yml")
        self.git("-c", "user.name=Test", "-c", "user.email=t@example.invalid",
                 "commit", "--quiet", "-m", "workflow")
        changed_commit = self.git("rev-parse", "HEAD")
        self.git("branch", "-f", "validated", changed_commit)
        changed_bundle = self.root / "changed.bundle"
        self.git("bundle", "create", str(changed_bundle), "refs/heads/validated")
        bytes_ = changed_bundle.read_bytes()
        changed = replace(snapshot, commit=changed_commit, bundle=bytes_,
                          bundle_sha256=hashlib.sha256(bytes_).hexdigest())
        credentials = []
        transport = GitHubGitTransport("example/disposable", self.repo,
            self.baseline, lambda *_args: credentials.append(1) or "unused",
            require_verified_stage=True)
        with self.assertRaisesRegex(KnownRejected, "workflow_approval_required"):
            transport("example/disposable", "git_push",
                {"branch": "run-branch", "commit": changed_commit},
                connection_id="connection-a", connection_generation=1,
                verified_stage=changed)
        self.assertEqual(credentials, [])

    def test_synthetic_push_classifies_and_sends_same_bare_repository(self):
        snapshot = self.resolve()
        seen = []
        def fake_git(args, **options):
            if "push" not in args:
                return _run_bounded_tree(args, **options)
            bare = Path(args[args.index("-C") + 1])
            verified = subprocess.run(
                ["git", "-C", str(bare), "rev-parse", "refs/stage/validated"],
                capture_output=True, check=True).stdout.strip()
            self.assertEqual(verified, snapshot.commit.encode())
            seen.append((bare, args))
            return subprocess.CompletedProcess(args, 0, b"", b"")
        credentials = []
        transport = GitHubGitTransport("example/disposable", self.repo,
            self.baseline, lambda *_args: credentials.append(1) or "synthetic-only",
            run=fake_git, require_verified_stage=True)
        transport._stage = lambda *_args: self.fail("checkout fallback used")
        self.verified.write_bytes(b"changed after resolution")
        result = transport("example/disposable", "git_push",
            {"branch": "run-branch", "commit": self.commit,
             "stage_attempt_id": "attempt-1"},
            connection_id="connection-a", connection_generation=1,
            verified_stage=snapshot)
        self.assertEqual(result["stage_digest"], snapshot.stage_digest)
        self.assertEqual(credentials, [1])
        self.assertEqual(len(seen), 1)
        self.assertFalse(seen[0][0].exists())
