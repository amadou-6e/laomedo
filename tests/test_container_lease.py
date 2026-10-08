"""Exact ownership and independent lease protocol tests, with no Docker daemon."""

import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from laomedo.container_lease import (cleanup_after_loss, cleanup_exact,
                                     inspect_exact, supervise,
                                     _detached_process_options)


class ContainerLeaseTests(unittest.TestCase):
    def test_supervisor_is_detached_from_runner_group(self):
        options = _detached_process_options()
        if "creationflags" in options:
            self.assertTrue(options["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP)
            self.assertTrue(options["creationflags"] & subprocess.CREATE_BREAKAWAY_FROM_JOB)
        else:
            self.assertEqual(options, {"start_new_session": True})

    def test_delayed_container_creation_is_removed(self):
        observations = iter([("absent", None), ("owned", "exact-id")])
        def observe(*_):
            return next(observations, ("absent", None))
        with patch("laomedo.container_lease.inspect_exact", side_effect=observe) as inspect, \
                patch("laomedo.container_lease.cleanup_exact", return_value=(True, "removed")) as cleanup:
            self.assertEqual(cleanup_after_loss("exact-name", "run-one", "token-one",
                                                watch_seconds=.01),
                             (True, "removed_after_loss"))
        self.assertGreaterEqual(inspect.call_count, 3)
        cleanup.assert_called_once_with("exact-name", "run-one", "token-one")

    def test_never_observed_does_not_claim_cleanup(self):
        with patch("laomedo.container_lease.inspect_exact", return_value=("absent", None)):
            self.assertEqual(cleanup_after_loss("exact-name", "run-one", "token-one",
                                                watch_seconds=.001),
                             (False, "never_observed"))

    def test_self_removed_between_inspection_and_cleanup_is_inconclusive(self):
        observations = iter([("owned", "exact-id")])
        with patch("laomedo.container_lease.inspect_exact",
                   side_effect=lambda *_: next(observations, ("absent", None))), \
             patch("laomedo.container_lease.cleanup_exact",
                   return_value=(True, "absent")):
            self.assertEqual(cleanup_after_loss("exact-name", "run-one", "token-one",
                                                watch_seconds=.001),
                             (False, "self_removed_after_observed"))

    def test_exact_identity_refuses_lookalike_container(self):
        entry = {"Id": "sha256:unrelated", "Name": "/laomedo-codex-looks-similar",
                 "Config": {"Labels": {"laomedo.run_id": "other",
                                       "laomedo.launch_token": "other"}}}
        with patch("laomedo.container_lease.subprocess.run", return_value=
                   subprocess.CompletedProcess([], 0, json.dumps([entry]), "")) as docker:
            self.assertEqual(inspect_exact("laomedo-codex-looks-similar",
                                           "run-one", "token-one"),
                             ("conflict", "sha256:unrelated"))
            self.assertEqual(cleanup_exact("laomedo-codex-looks-similar",
                                           "run-one", "token-one"),
                             (False, "conflict"))
            self.assertEqual(docker.call_count, 2)
            self.assertTrue(all(call.args[0][1] == "inspect" for call in docker.call_args_list))

    def test_cleanup_removes_container_id_not_name(self):
        entry = {"Id": "sha256:owned", "Name": "/exact-name",
                 "Config": {"Labels": {"laomedo.run_id": "run-one",
                                       "laomedo.launch_token": "token-one"}}}
        responses = [subprocess.CompletedProcess([], 0, json.dumps([entry]), ""),
                     subprocess.CompletedProcess([], 0, "", ""),
                     subprocess.CompletedProcess([], 1, "", "No such object: exact-name")]
        with patch("laomedo.container_lease.subprocess.run", side_effect=responses) as docker:
            self.assertEqual(cleanup_exact("exact-name", "run-one", "token-one"),
                             (True, "removed"))
            self.assertEqual(docker.call_args_list[1].args[0],
                             ["docker", "rm", "-f", "sha256:owned"])

    def test_eof_runs_cleanup_after_ready_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record = root / "record.json"
            record.write_text(json.dumps({"run_id": "run-one", "container_ownership": {
                "name": "exact-name", "launch_token": "token-one"}}), encoding="utf-8")
            ready, result = root / "ready", root / "result.json"
            with patch("laomedo.container_lease.sys.stdin", io.StringIO("")), \
                    patch("laomedo.container_lease.cleanup_after_loss", return_value=(True, "removed")) as cleanup:
                self.assertEqual(supervise(record, "exact-name", "run-one", "token-one",
                                           ready, result), 0)
            self.assertEqual(ready.read_text(encoding="utf-8"), "token-one")
            self.assertEqual(json.loads(result.read_text(encoding="utf-8")),
                             {"reason": "eof", "cleanup_verified": True, "state": "removed"})
            cleanup.assert_called_once_with("exact-name", "run-one", "token-one")


if __name__ == "__main__":
    unittest.main()
