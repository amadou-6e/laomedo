import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from laomedo.bundle_stage_ownership import reserve_container, stage_lock, reconcile_orphan


class BundleStageOwnershipTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.attempt = Path(temp.name)
        self.owner = {"name": "laomedo-bundle-stage-" + "a" * 16,
                      "token": "b" * 64, "image_id": "sha256:" + "c" * 64}
        reserve_container(self.attempt, self.owner)
        self.calls = []

    def docker(self, args, timeout):
        self.calls.append(args)
        if args[1] == "rm":
            self.removed = True
            return subprocess.CompletedProcess(args, 0, "", "")
        if getattr(self, "removed", False):
            return subprocess.CompletedProcess(args, 1, "", "No such object: stage")
        config = {"Name": "/" + self.owner["name"], "Id": "d" * 64,
                  "Image": self.owner["image_id"],
                  "Config": {"Labels": {"laomedo.bundle-stage": self.owner["name"],
                      "laomedo.bundle-stage-token": self.owner["token"]}}}
        if getattr(self, "conflict", False):
            config["Config"]["Labels"]["laomedo.bundle-stage-token"] = "wrong"
        return subprocess.CompletedProcess(args, 0, json.dumps([config]), "")

    def test_reservation_is_exclusive(self):
        with self.assertRaises(FileExistsError):
            reserve_container(self.attempt, self.owner)
        self.assertEqual(self.calls, [])

    def test_active_lock_prevents_cleanup_by_another_worker(self):
        with stage_lock(self.attempt) as acquired:
            self.assertTrue(acquired)
            self.assertIsNone(reconcile_orphan(self.attempt, docker=self.docker))
        self.assertEqual(self.calls, [])

    def test_orphan_cleanup_double_checks_then_removes_by_id(self):
        self.assertTrue(reconcile_orphan(self.attempt, docker=self.docker)["cleanup_verified"])
        self.assertEqual([c[1] for c in self.calls], ["inspect", "inspect", "rm", "inspect"])
        self.assertEqual(self.calls[2][-1], "d" * 64)
        self.assertFalse(any(c[1] in {"start", "create"} for c in self.calls))

    def test_lookalike_is_not_removed(self):
        self.conflict = True
        self.assertEqual(reconcile_orphan(self.attempt, docker=self.docker),
                         {"cleanup_verified": False, "detail": "conflict"})
        self.assertFalse(any(c[1] == "rm" for c in self.calls))

    def test_absence_is_not_verified_and_late_container_is_removed(self):
        self.removed = True
        self.assertFalse(reconcile_orphan(self.attempt, docker=self.docker)["cleanup_verified"])
        self.removed = False
        self.assertTrue(reconcile_orphan(self.attempt, docker=self.docker)["cleanup_verified"])

    def test_daemon_failure_is_not_absence(self):
        def unavailable(args, timeout):
            return subprocess.CompletedProcess(args, 1, "", "connection refused")
        self.assertEqual(reconcile_orphan(self.attempt, docker=unavailable),
                         {"cleanup_verified": False, "detail": "unknown"})

    def test_malformed_inspection_never_removes_or_crashes(self):
        for value in (["bad"], [{"Config": "bad"}], [{"Config": {}, "Id": 1}]):
            def malformed(args, timeout):
                self.calls.append(args)
                return subprocess.CompletedProcess(args, 0, json.dumps(value), "")
            with self.subTest(value=value):
                self.assertFalse(reconcile_orphan(self.attempt, docker=malformed)["cleanup_verified"])
        self.assertFalse(any(c[1] == "rm" for c in self.calls))
