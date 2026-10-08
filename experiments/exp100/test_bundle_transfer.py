"""Local, credential-free checks for EXP-100/S2's staged-object path."""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
import os
import socket
import stat
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from experiments.exp100.bundle_transfer import git, git_env, verify_bundle


REF = "refs/heads/run-a"


class BundleTransferTests(unittest.TestCase):
    def setUp(self):
        self.capture = None
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.agent = self.root / "agent"
        self.source.mkdir()
        self._git(self.source, "init", "--quiet")
        (self.source / "base.txt").write_bytes(b"baseline\n")
        self._commit(self.source, "base")
        self.baseline = self._git(self.source, "rev-parse", "HEAD").stdout.decode().strip()
        self._git(None, "clone", "--quiet", str(self.source), str(self.agent))
        self._git(self.agent, "checkout", "-q", "-b", "run-a")
        (self.agent / "change.txt").write_bytes(b"first\n")
        self._commit(self.agent, "first")
        self.first = self._git(self.agent, "rev-parse", "HEAD").stdout.decode().strip()

    def _git(self, directory, *args):
        env = git_env()
        env.update({"GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
                    "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
                    "GIT_AUTHOR_DATE": "2020-01-01T00:00:00+00:00",
                    "GIT_COMMITTER_DATE": "2020-01-01T00:00:00+00:00"})
        result = git(list(args), directory=directory, env=env)
        self.assertEqual(result.returncode, 0, (args, result.stderr.decode(errors="replace")))
        return result

    def _commit(self, directory, message):
        self._git(directory, "add", "-A")
        self._git(directory, "commit", "--quiet", "-m", message)

    def _bundle(self, filename, *refs):
        path = self.root / filename
        self._git(self.agent, "bundle", "create", str(path), *refs)
        return path.read_bytes()

    def _verify(self, data, **overrides):
        args = {"trusted_source": self.source, "baseline": self.baseline,
                "expected_ref": REF}
        args.update(overrides)
        result = verify_bundle(data, **args)
        if self.capture is not None:
            self.capture.append({"bundle_sha256": hashlib.sha256(data).hexdigest(),
                                 "reason": result["reason"], "stage": result["stage"],
                                 "commit": result["commit"], "tree": result["tree"]})
        return result

    def _control_import(self, data):
        stage = self.root / ("control-" + str(len(list(self.root.glob("control-*")))))
        bundle = self.root / (stage.name + ".bundle")
        bundle.write_bytes(data)
        self._git(None, "init", "--bare", "--quiet", str(stage))
        self._git(stage, "fetch", "--no-tags", str(self.source), self.baseline)
        self._git(stage, "bundle", "unbundle", str(bundle))

    def test_first_commit_import_and_exact_ref(self):
        data = self._bundle("first.bundle", "run-a")
        result = self._verify(data)
        self.assertEqual(result["reason"], "accepted", result)
        self.assertEqual(result["commit"], self.first)
        self.assertEqual(result["stage"], "complete")
        self.assertIsNotNone(result["tree"])
        self.assertEqual(self._verify(data, expected_ref="refs/heads/other")["reason"],
                         "ref_name")
        self._control_import(data)

    def test_second_commit_requires_host_confirmed_seed(self):
        first_bundle = self._bundle("first.bundle", "run-a")
        host = self.root / "host.git"
        self._git(None, "init", "--bare", "--quiet", str(host))
        self._git(host, "fetch", "--no-tags", str(self.source), self.baseline)
        self._git(host, "bundle", "unbundle", str(self.root / "first.bundle"))
        self.assertEqual(self._verify(first_bundle)["reason"], "accepted")
        journal = self.root / "host-confirmed.json"
        journal.write_text(json.dumps({"run_ref": REF, "confirmed_commit": self.first}),
                           encoding="utf-8")
        (self.agent / "change.txt").write_bytes(b"second\n")
        self._commit(self.agent, "second")
        second = self._git(self.agent, "rev-parse", "HEAD").stdout.decode().strip()
        thin = self._bundle("second.bundle", self.first + "..run-a")
        self.assertEqual(self._verify(thin)["reason"], "missing_prerequisite")
        confirmed = json.loads(journal.read_text(encoding="utf-8"))
        self.assertEqual(confirmed["run_ref"], REF)
        accepted = self._verify(thin, trusted_source=host,
                                confirmed_commit=confirmed["confirmed_commit"])
        self.assertEqual(accepted["reason"], "accepted", accepted)
        self.assertEqual(accepted["commit"], second)

    def test_extra_ref_and_truncated_pack_are_not_accepted(self):
        self._git(self.agent, "branch", "extra")
        extra = self._bundle("extra.bundle", "run-a", "extra")
        self._control_import(extra)
        self.assertEqual(self._verify(extra)["reason"], "ref_count")
        good = self._bundle("good.bundle", "run-a")
        self.assertEqual(self._verify(good)["reason"], "accepted")
        truncated = good[:-20]
        bad = self._verify(truncated)
        self.assertEqual((bad["reason"], bad["stage"]),
                         ("object_invalid", "import"), bad)

    def test_unrelated_history_and_workflow_diff(self):
        self._git(self.agent, "checkout", "-q", "--orphan", "unrelated")
        self._git(self.agent, "rm", "-q", "-rf", ".")
        (self.agent / "unrelated.txt").write_bytes(b"unrelated\n")
        self._commit(self.agent, "unrelated")
        unrelated = self._bundle("unrelated.bundle", "unrelated")
        # Header ref rename is the only mutation: the pack remains valid.
        unrelated = unrelated.replace(b"refs/heads/unrelated\n", b"refs/heads/run-a\n", 1)
        self._control_import(unrelated)
        self.assertEqual(self._verify(unrelated)["reason"], "baseline_ancestry")
        self._git(self.agent, "checkout", "-q", "run-a")
        workflow = self.agent / ".github" / "workflows" / "check.yml"
        workflow.parent.mkdir(parents=True)
        workflow.write_bytes(b"name: check\n")
        self._commit(self.agent, "workflow")
        workflow_data = self._bundle("workflow.bundle", "run-a")
        self._control_import(workflow_data)
        self.assertEqual(self._verify(workflow_data)["reason"],
                         "workflow_change")

    def test_bundle_capabilities_and_tag_object(self):
        good = self._bundle("good.bundle", "run-a")
        self.assertEqual(self._verify(good)["reason"], "accepted")
        v3 = good.replace(b"# v2 git bundle\n", b"# v3 git bundle\n", 1)
        filtered = v3.replace(b"# v3 git bundle\n",
                              b"# v3 git bundle\n@filter=blob:none\n", 1)
        self.assertEqual(self._verify(filtered)["reason"], "bundle_version")
        different_format = v3.replace(b"# v3 git bundle\n",
                                      b"# v3 git bundle\n@object-format=sha256\n", 1)
        self.assertEqual(self._verify(different_format)["reason"], "object_format")
        self.assertEqual(self._verify(v3)["reason"], "accepted")
        self._git(self.agent, "tag", "-a", "tagged", "-m", "tagged")
        tagged = self._bundle("tag.bundle", "tagged")
        tagged = tagged.replace(b"refs/tags/tagged\n", b"refs/heads/run-a\n", 1)
        self._control_import(tagged)
        result = self._verify(tagged)
        self.assertEqual((result["reason"], result["stage"]),
                         ("ref_type", "type"), result)

    def test_host_global_and_inherited_trace_controls(self):
        bundle = self._bundle("first.bundle", "run-a")
        hostile_home = self.root / "host-home"
        hostile_home.mkdir()
        config = hostile_home / ".gitconfig"
        global_trace = self.root / "global-trace.log"
        inherited_trace = self.root / "inherited-trace.log"
        config.write_text("[trace2]\n\tnormalTarget = " +
                          global_trace.as_posix() + "\n", encoding="utf-8")
        control_env = git_env(home=hostile_home)
        control_env.pop("GIT_CONFIG_GLOBAL", None)
        loaded = git(["config", "--global", "--get", "trace2.normalTarget"],
                     env=control_env)
        self.assertEqual(loaded.stdout.decode().strip(), global_trace.as_posix())
        control = git(["status", "--porcelain"], directory=self.source,
                      env=control_env)
        self.assertEqual(control.returncode, 0)
        self.assertTrue(global_trace.exists(), "global config control did not fire")
        global_trace.unlink()
        control = git(["status", "--porcelain"], directory=self.source,
                      env=git_env(trace=str(inherited_trace)))
        self.assertEqual(control.returncode, 0)
        self.assertTrue(inherited_trace.exists(), "inherited trace control did not fire")
        inherited_trace.unlink()
        with patch.dict(os.environ, {"HOME": str(hostile_home),
                                     "USERPROFILE": str(hostile_home),
                                     "XDG_CONFIG_HOME": str(hostile_home),
                                     "GIT_TRACE": str(inherited_trace)}):
            self.assertEqual(self._verify(bundle)["reason"], "accepted")
        self.assertFalse(global_trace.exists())
        self.assertFalse(inherited_trace.exists())

    def test_complete_pack_with_missing_object_is_rejected_at_integrity(self):
        def raw_git(args, payload):
            env = git_env()
            env.update({"HOME": str(self.root), "USERPROFILE": str(self.root),
                        "XDG_CONFIG_HOME": str(self.root)})
            result = subprocess.run(["git", "-C", str(self.agent), *args],
                                    input=payload, capture_output=True,
                                    timeout=10, check=False, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout

        def handmade_bundle(blob: bytes, *, include_blob: bool):
            tree = raw_git(["hash-object", "--literally", "-t", "tree", "-w",
                            "--stdin"], b"100644 missing.txt\x00" + blob).strip()
            commit_data = (b"tree " + tree + b"\nparent " +
                           self.baseline.encode() +
                           b"\nauthor Fixture <fixture@example.invalid> "
                           b"1577836800 +0000\ncommitter Fixture "
                           b"<fixture@example.invalid> 1577836800 +0000\n\ninvalid\n")
            commit = raw_git(["hash-object", "--literally", "-t", "commit",
                              "-w", "--stdin"], commit_data).strip()
            objects = commit + b"\n" + tree + b"\n"
            if include_blob:
                objects += blob.hex().encode() + b"\n"
            pack = raw_git(["pack-objects", "--stdout"], objects)
            return b"# v2 git bundle\n" + commit + b" refs/heads/run-a\n\n" + pack

        present = raw_git(["hash-object", "-t", "blob", "-w", "--stdin"],
                          b"present\n").strip()
        control = handmade_bundle(bytes.fromhex(present.decode()), include_blob=True)
        self.assertEqual(self._verify(control)["reason"], "accepted")
        missing = bytes.fromhex("11" * 20)
        bundle = handmade_bundle(missing, include_blob=False)
        result = self._verify(bundle)
        self.assertEqual(result["reason"], "object_invalid", result)
        self.assertIn(result["stage"], {"import", "integrity"})

    def test_agent_hook_detector_fires_only_in_agent(self):
        bundle = self._bundle("first.bundle", "run-a")
        hook = self.agent / ".git" / "hooks" / "pre-commit"
        sentinel = self.agent / "hook-sentinel.txt"
        hook.write_bytes(b"#!/bin/sh\necho fired > hook-sentinel.txt\n")
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
        self._git(self.agent, "commit", "--allow-empty", "--quiet", "-m", "control")
        self.assertTrue(sentinel.exists(), "hook positive control did not fire")
        sentinel.unlink()
        self.assertEqual(self._verify(bundle)["reason"], "accepted")
        self.assertFalse(sentinel.exists(), "host stage invoked agent hook")

    def test_host_never_contacts_agent_remote(self):
        bundle = self._bundle("first.bundle", "run-a")
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(listener.close)
        listener.bind(("127.0.0.1", 0))
        listener.listen(2)
        listener.settimeout(2)
        contacts = []
        stop = threading.Event()

        def accept():
            while not stop.is_set():
                try:
                    connection, _ = listener.accept()
                except (OSError, socket.timeout):
                    continue
                contacts.append(True)
                connection.close()

        worker = threading.Thread(target=accept, daemon=True)
        worker.start()
        url = f"git://127.0.0.1:{listener.getsockname()[1]}/hostile"
        self._git(self.agent, "remote", "set-url", "origin", url)
        # Positive control: Git contacts the hostile URL when instructed.
        control = git(["ls-remote", url], directory=self.agent)
        self.assertNotEqual(control.returncode, 0)
        self.assertEqual(len(contacts), 1, "remote detector did not fire")
        hostile_home = self.root / "rewrite-home"
        hostile_home.mkdir()
        (hostile_home / ".gitconfig").write_text(
            f'[url "{url}"]\n\tinsteadOf = https://hostile.invalid/hostile\n',
            encoding="utf-8")
        control_env = git_env(home=hostile_home)
        control_env.pop("GIT_CONFIG_GLOBAL", None)
        rewritten = git(["ls-remote", "https://hostile.invalid/hostile"],
                        directory=self.agent, env=control_env)
        self.assertNotEqual(rewritten.returncode, 0)
        self.assertEqual(len(contacts), 2, "global rewrite detector did not fire")
        self.assertEqual(self._verify(bundle)["reason"], "accepted")
        self.assertEqual(len(contacts), 2, "host stage contacted hostile remote")
        stop.set()

    def test_post_export_agent_alternates_and_replace_refs_do_not_change_stage(self):
        bundle = self._bundle("first.bundle", "run-a")
        before = self._verify(bundle)
        self.assertEqual(before["reason"], "accepted")
        alternate = self.agent / ".git" / "objects" / "info" / "alternates"
        alternate.write_text((self.source / ".git" / "objects").as_posix() + "\n",
                             encoding="utf-8", newline="\n")
        replacement = self.agent / ".git" / "refs" / "replace" / self.first
        replacement.parent.mkdir(parents=True, exist_ok=True)
        replacement.write_text(self.baseline + "\n", encoding="ascii", newline="\n")
        control_env = git_env()
        control_env.pop("GIT_NO_REPLACE_OBJECTS", None)
        visible = git(["rev-parse", self.first + "^{tree}"],
                      directory=self.agent, env=control_env)
        self.assertEqual(visible.returncode, 0, visible.stderr)
        self.assertNotEqual(visible.stdout.decode().strip(), before["tree"],
                            "replace-ref detector did not fire")
        after = self._verify(bundle)
        self.assertEqual(after, before, "host decision changed with agent repository")


if __name__ == "__main__":
    unittest.main()
