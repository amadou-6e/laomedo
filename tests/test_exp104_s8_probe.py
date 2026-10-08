"""Fail-closed controls for the unexecuted EXP-104 S8 live probe."""

import json
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from laomedo.github_mediation import MediationStore
from laomedo.lease_service import LeaseService
from laomedo.mediation_authority import RunGrantAuthority
from laomedo.mediation_service import MediationHTTPService

_probe_path = Path(__file__).resolve().parents[1] / "experiments" / "exp104" / "s8_probe.py"
_probe_spec = importlib.util.spec_from_file_location("exp104_s8_probe", _probe_path)
if _probe_spec is None or _probe_spec.loader is None:
    raise RuntimeError("s8_probe_unavailable")
probe = importlib.util.module_from_spec(_probe_spec)
_probe_spec.loader.exec_module(probe)


class S8ProbeTests(unittest.TestCase):
    def test_agent_process_environment_drops_host_token_override(self):
        with patch.dict(os.environ, {"GH_LAOMEDO": "synthetic-provider-token",
                                  "LAOMEDO_MEDIATED_GIT_TOKEN": "another-secret"}):
            environment = probe._agent_environment()
        self.assertNotIn("GH_LAOMEDO", environment)
        self.assertNotIn("LAOMEDO_MEDIATED_GIT_TOKEN", environment)

    def test_preflight_requires_exact_repo_and_absent_markers(self):
        def api(_token, path):
            if path.endswith("/user"):
                return {"login": "ga84jog"}
            if path.endswith("/git/ref/heads/main"):
                return {"object": {"sha": probe.BASELINE}}
            return {"id": probe.REPOSITORY_ID, "default_branch": "main",
                    "permissions": {"push": True}}

        with patch.object(probe, "_api", side_effect=api), \
             patch.object(probe, "_absent_ref") as absent, \
             patch.object(probe, "_read_list", return_value=[]), \
             patch.object(probe.subprocess, "run", return_value=subprocess.CompletedProcess(
                 [], 0, b"", b"")):
            probe._preflight("synthetic")
        self.assertEqual(absent.call_count, 2)

        with patch.object(probe, "_api", side_effect=api), \
             patch.object(probe, "_absent_ref"), \
             patch.object(probe, "_read_list", return_value=[{
                 "body": probe.MARKERS["a"]}]), \
             self.assertRaisesRegex(RuntimeError, "pr_marker_preflight_uncertain"):
            probe._preflight("synthetic")

    def test_inconclusive_write_does_not_count_as_confirmed(self):
        for status, response in ((200, {"state": "unknown"}),
                                 (500, {"state": "confirmed", "result": {}}),
                                 (200, {"state": "confirmed", "result": []})):
            with self.subTest(status=status, response=response), \
                 self.assertRaisesRegex(RuntimeError, "no_retry"):
                probe._check_effect(status, response, "sample")

    def test_client_response_must_not_expose_secrets(self):
        with patch.object(probe.subprocess, "run", return_value=subprocess.CompletedProcess(
                [], 0, '{"state":"confirmed","secret":"provider-token"}', "")), \
             self.assertRaisesRegex(RuntimeError, "secret_in_agent_response"):
            probe._container_call("synthetic", "pr_create", {}, "effect",
                                  ("provider-token", "run-capability"))

    def test_review_record_binds_exact_identity_and_head(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.json"
            path.write_text(json.dumps({"identity": probe.IDENTITY,
                                        "source_sha": "abc", "verdict": "approve"}),
                            encoding="utf-8")
            self.assertEqual(len(probe._reviewed_record(path, "abc")), 64)
            with self.assertRaisesRegex(RuntimeError, "pre_run_review_not_approved"):
                probe._reviewed_record(path, "def")

    def test_reviewed_source_refuses_uncommitted_change(self):
        with patch.object(probe.subprocess, "run", return_value=subprocess.CompletedProcess(
                [], 0, b" M experiments/exp104/s8_probe.py\n", b"")), \
             self.assertRaisesRegex(RuntimeError, "reviewed_source_not_clean"):
            probe._require_clean_source(Path("synthetic"))
        with patch.object(probe.subprocess, "run", return_value=subprocess.CompletedProcess(
                [], 0, b"", b"")):
            probe._require_clean_source(Path("synthetic"))

    def test_run_refuses_wrong_identity_before_token_or_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(probe, "HostTokenConnection") as connection, \
                 self.assertRaisesRegex(RuntimeError, "specific_live_approval_required"):
                probe.run(Path(directory) / "fresh", Path(directory) / "token",
                          "abc", "other-identity", Path(directory) / "review")
            connection.assert_not_called()

    def test_scan_rejects_token_in_agent_mount(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            for side in ("a", "b"):
                (state / ("agent-" + side)).mkdir()
            (state / "agent-a" / "leak.txt").write_text("provider-token")
            with patch.object(probe.subprocess, "run", return_value=subprocess.CompletedProcess(
                    [], 0, b"safe", b"")), \
                 self.assertRaisesRegex(RuntimeError, "secret_in_agent_mount"):
                probe._scan_agent_exposure(state, "provider-token", ("cap-a", "cap-b"))

    def test_persisted_scan_allows_only_designated_capability_file(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            secret = state / "lease" / "leases" / "lease-a" / "grant.secret"
            secret.parent.mkdir(parents=True)
            secret.write_text("cap-a", encoding="utf-8")
            self.assertEqual(probe._scan_persisted_exposure(
                state, "provider-token", ("cap-a",))["unexpected_exact_hits"], 0)
            (state / "observation.json").write_text("cap-a", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "capability_outside_designated_mount"):
                probe._scan_persisted_exposure(state, "provider-token", ("cap-a",))

    @unittest.skipUnless(os.name == "nt" and
                         os.environ.get("LAOMEDO_DOCKER_MEDIATION_TEST") == "1",
                         "requires pinned image and Windows Docker Desktop route")
    def test_s8_runner_uses_its_mounted_capability_with_synthetic_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state / "mediator").mkdir()
            store = MediationStore(state / "mediator" / "mediator.sqlite")
            authority = RunGrantAuthority(state / "authority.sqlite")
            lease = LeaseService(state / "lease", mediator=store,
                                 mediation_authority=authority.authorize_lease)
            calls = []

            def fake_transport(repository, operation, payload, **_binding):
                calls.append((repository, operation, payload))
                return {"synthetic": True}

            mediator = MediationHTTPService(store, fake_transport)
            status = {"pid": os.getpid(), "port": mediator.port,
                      "instance": mediator.instance,
                      "repository": probe.REPOSITORY}
            (state / "mediator" / "mediator.json").write_text(json.dumps(status))
            mediator_thread = threading.Thread(target=mediator.serve, daemon=True)
            lease_thread = threading.Thread(target=lease.serve, daemon=True)
            mediator_thread.start()
            lease_thread.start()
            local_name = "laomedo-s8-synthetic-" + str(os.getpid())
            runner = None
            try:
                probe._wait(state / "lease" / "service.json", 5)
                reference = authority.approve(
                    invocation_id="invocation-" + probe.RUNS["a"],
                    repository=probe.REPOSITORY, branch=probe.BRANCHES["a"],
                    operations={"actions_read"}, reviewed_by="synthetic-test")
                authority.bind_run(reference, probe.RUNS["a"])
                script = (
                    "from pathlib import Path; "
                    "from experiments.exp104 import s8_probe as p; "
                    f"p.NAMES['a']={local_name!r}; "
                    "p._agent_runner(Path(__import__('sys').argv[1]), 'a', "
                    "Path(__import__('sys').argv[2]))"
                )
                ready = state / "ready.json"
                runner = subprocess.Popen([__import__("sys").executable, "-c", script,
                                           str(state), str(ready)],
                                          stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL)
                probe._wait(ready, 25)
                status_code, response = probe._container_call(
                    local_name, "actions_read", {"resource": "runs"},
                    "synthetic-read", ("synthetic-provider-token",))
                self.assertEqual(status_code, 200)
                self.assertEqual(response["state"], "confirmed")
                self.assertEqual(calls, [(probe.REPOSITORY, "actions_read",
                                          {"resource": "runs"})])
                stopped = subprocess.run(["docker", "stop", local_name],
                                         capture_output=True, timeout=20)
                self.assertEqual(stopped.returncode, 0)
                runner.wait(timeout=20)
                self.assertEqual(probe._wait(state / "lease" / "leases" /
                                             probe.LEASES["a"] / "result.json", 20)[
                                                 "reason"], "done")
            finally:
                if runner is not None and runner.poll() is None:
                    runner.kill()
                    runner.wait(timeout=5)
                # Only this exact test container may be removed.
                subprocess.run(["docker", "rm", "-f", local_name],
                               capture_output=True, timeout=20)
                lease.stopping.set()
                mediator.close()
                lease_thread.join(timeout=5)
                mediator_thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
