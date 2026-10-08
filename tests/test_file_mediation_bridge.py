"""Credential-free file routing through the real mediator ledger."""

import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

from laomedo.file_mediation_bridge import FileMediationBridge
from laomedo.github_mediation import MediationStore
from laomedo.local_runner import _docker_prefix


class FileBridgeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.runs = self.root / "runs"
        self.leases = self.root / "lease" / "leases"
        self.runs.mkdir()
        self.leases.mkdir(parents=True)
        self.store = MediationStore(self.root / "mediator.sqlite")
        self.calls = []

        def fake_transport(repository, operation, payload, **_binding):
            self.calls.append((repository, operation, payload))
            return {"synthetic": True}

        self.bridge = FileMediationBridge(
            self.runs, self.root / "lease", self.store, fake_transport,
            self.root / "private" / "bridge.jsonl")

    def add_run(self, branch, number):
        run_id, lease_token = str(uuid4()), uuid4().hex
        grant_id, secret = self.store.issue(
            run_id=run_id, invocation_id="invocation-" + run_id,
            repository="example/disposable", branch=branch,
            operations={"pr_update"}, target_prs={number: "main"},
            ttl_seconds=60, lease_token=lease_token,
            lease_scope="test-service", service_instance="test-instance")
        run = self.runs / run_id
        run.mkdir()
        for name in ("workspace", "bridge-spool", "bridge-responses"):
            (run / name).mkdir()
        (run / "record.json").write_text(json.dumps({
            "run_id": run_id,
            "container_ownership": {"launch_token": lease_token,
                                    "grant_id": grant_id}}), encoding="utf-8")
        lease = self.leases / lease_token
        lease.mkdir()
        (lease / "lease.json").write_text(json.dumps({
            "run_id": run_id, "token": lease_token}), encoding="utf-8")
        (lease / "accepted.json").write_text(json.dumps({
            "token": lease_token, "grant_id": grant_id}), encoding="utf-8")
        (lease / "grant.secret").write_text(secret, encoding="utf-8")
        return run_id, secret, run

    def request(self, run, effect, branch, number, **changes):
        body = {"repository": "example/disposable", "operation": "pr_update",
                "payload": {"number": number, "head": branch, "base": "main",
                            "marker": "phase-c"}, "effect_id": effect}
        body.update(changes)
        (run / "workspace" / (".laomedo-req-" + effect + ".json")).write_text(
            json.dumps(body), encoding="utf-8")
        return body

    def response(self, run, effect):
        return json.loads((run / "bridge-responses" / (effect + ".json")).read_text(
            encoding="utf-8"))

    def test_confirmed_then_revoked_a_does_not_stop_b(self):
        a_id, a_secret, a = self.add_run("phase-c-a", 7)
        _, _, b = self.add_run("phase-c-b", 8)
        self.request(a, "effect-a-1", "phase-c-a", 7)
        self.request(b, "effect-b-1", "phase-c-b", 8)
        self.assertEqual(self.bridge.poll_once(), 2)
        self.assertEqual(self.response(a, "effect-a-1")["state"], "confirmed")
        self.assertEqual(self.response(b, "effect-b-1")["state"], "confirmed")
        self.assertEqual(len(self.calls), 2)

        self.store.revoke_run(a_id)
        self.request(a, "effect-a-2", "phase-c-a", 7)
        self.request(b, "effect-b-2", "phase-c-b", 8)
        self.assertEqual(self.bridge.poll_once(), 2)
        self.assertEqual(self.response(a, "effect-a-2")["error"],
                         "grant_unavailable")
        self.assertEqual(self.response(b, "effect-b-2")["state"], "confirmed")
        self.assertEqual(len(self.calls), 3)
        journal = (self.root / "private" / "bridge.jsonl").read_text()
        self.assertNotIn(a_secret, journal)
        self.assertIn('"provider_called": false', journal)

    def test_bridge_restart_recovers_claimed_effect_without_duplicate_call(self):
        _, _, run = self.add_run("phase-c-a", 7)
        self.request(run, "effect-a", "phase-c-a", 7)
        source = run / "workspace" / ".laomedo-req-effect-a.json"
        os.replace(source, run / "bridge-spool" / source.name)
        self.assertEqual(self.bridge.poll_once(), 1)
        self.assertEqual(self.response(run, "effect-a")["state"], "confirmed")
        self.assertEqual(self.bridge.poll_once(), 0)
        self.assertEqual(len(self.calls), 1)

    def test_replay_after_revocation_returns_recorded_effect(self):
        run_id, _, run = self.add_run("phase-c-a", 7)
        self.request(run, "effect-a", "phase-c-a", 7)
        self.assertEqual(self.bridge.poll_once(), 1)
        (run / "bridge-responses" / "effect-a.json").unlink()
        self.store.revoke_run(run_id)
        self.assertEqual(self.bridge.poll_once(), 1)
        self.assertEqual(self.response(run, "effect-a")["state"], "confirmed")
        self.assertEqual(len(self.calls), 1)
        journal = [json.loads(line) for line in
                   (self.root / "private" / "bridge.jsonl").read_text().splitlines()]
        self.assertTrue(journal[-1]["replayed"])
        self.assertFalse(journal[-1]["provider_called"])

    def test_invalid_files_never_reach_transport(self):
        _, _, run = self.add_run("phase-c-a", 7)
        source = run / "workspace" / ".laomedo-req-bad.json"
        source.write_text("{", encoding="utf-8")
        self.assertEqual(self.bridge.poll_once(), 1)
        self.assertEqual(self.response(run, "bad")["error"], "request_invalid")
        self.assertEqual(self.calls, [])

        target = run / "workspace" / "target.json"
        target.write_text("{}", encoding="utf-8")
        linked = run / "workspace" / ".laomedo-req-link.json"
        try:
            os.link(target, linked)
        except OSError:
            self.skipTest("hard links unavailable")
        self.assertEqual(self.bridge.poll_once(), 1)
        self.assertEqual(self.response(run, "link")["error"], "request_invalid")
        self.assertEqual(self.calls, [])

    def test_nested_request_does_not_poison_worker(self):
        _, _, run = self.add_run("phase-c-a", 7)
        (run / "workspace" / ".laomedo-req-deep.json").write_text(
            '{"effect_id":"deep","payload":' + "[" * 20000 + "0" + "]" * 20000 + "}",
            encoding="utf-8")
        self.request(run, "good", "phase-c-a", 7)
        self.assertEqual(self.bridge.poll_once(), 2)
        self.assertEqual(self.response(run, "deep")["error"], "request_invalid")
        self.assertEqual(self.response(run, "good")["state"], "confirmed")
        self.assertEqual(len(self.calls), 1)

    def test_status_replace_retries_reader_sharing_violation(self):
        stop = threading.Event()
        original = os.replace
        attempts = []

        def replace(source, target):
            if str(target).endswith("file-bridge.json") and len(attempts) < 2:
                attempts.append(1)
                raise PermissionError("sharing violation")
            return original(source, target)

        with patch("laomedo.file_mediation_bridge.os.replace", side_effect=replace), \
             patch.object(self.bridge, "poll_once", side_effect=lambda: stop.set()):
            self.bridge.serve(stop, self.root / "file-bridge.json")
        self.assertEqual(len(attempts), 2)
        self.assertTrue((self.root / "file-bridge.json").exists())

    def test_one_response_write_failure_does_not_starve_other_run(self):
        _, _, a = self.add_run("phase-c-a", 7)
        _, _, b = self.add_run("phase-c-b", 8)
        self.request(a, "bad", "phase-c-a", 7)
        self.request(b, "good", "phase-c-b", 8)
        original = self.bridge._record

        def record(value):
            if value.get("effect_id") == "bad" and value.get("category") is None:
                raise OSError("synthetic_journal_failure")
            return original(value)

        with patch.object(self.bridge, "_record", side_effect=record):
            self.bridge.poll_once()
        self.assertEqual(self.response(b, "good")["state"], "confirmed")
        self.assertFalse((a / "bridge-responses" / "bad.json").exists())
        self.assertEqual(len(self.calls), 2)
        self.bridge.poll_once()
        self.assertEqual(self.response(a, "bad")["state"], "confirmed")
        self.assertEqual(len(self.calls), 2)

    def test_file_mount_has_no_agent_bearer_or_url(self):
        run = self.root / "run"
        for name in ("workspace", "canonical", "store", "bridge-responses"):
            (run / name).mkdir(parents=True)
        args = _docker_prefix(run / "workspace", run / "canonical", run / "store",
                              file_responses=run / "bridge-responses")
        joined = " ".join(args)
        self.assertIn("target=/run/laomedo/responses,readonly", joined)
        self.assertNotIn("target=/run/laomedo/capability", joined)
        self.assertNotIn("LAOMEDO_MEDIATOR_URL", joined)
