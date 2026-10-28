"""Exact ownership and independent lease protocol tests, with no Docker daemon."""

from laomedo.host.leases.models import ContainerIdentity

import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from laomedo.host.leases.utils import cleanup_after_loss; from laomedo.host.leases.utils import cleanup_exact; from laomedo.host.leases.utils import inspect_exact; from laomedo.host.leases.utils import supervise; from laomedo.host.leases.utils import _detached_process_options


class ContainerLeaseTests(unittest.TestCase):
    @unittest.skipUnless(__import__("importlib.util").util.find_spec("py_docker"), "Requires optional Docker runtime")
    def test_cleanup_uses_original_endpoint_and_runtime_ownership(self):
        identity=ContainerIdentity(name="exact",run_id="run",token="private",docker_endpoint="unix:///original.sock")
        with patch("py_docker.Client") as client:
            watch=client.return_value.__enter__.return_value.containers.watch.return_value
            from py_docker.containers.models import ContainerObservation, ContainerIdentity as RuntimeIdentity
            watch.inspect.return_value=ContainerObservation(state="owned",identity=RuntimeIdentity(id="a"*64,name="exact",labels={"owner":"private"}))
            watch.cleanup.return_value.verified=True
            watch.cleanup.return_value.detail="removed"
            self.assertEqual(inspect_exact(identity),("owned","a"*64))
            self.assertEqual(cleanup_exact(identity),(True,"removed"))
            client.assert_called_with(environment={"DOCKER_HOST":"unix:///original.sock"})
            reservation=client.return_value.__enter__.return_value.containers.watch.call_args.args[0]
            self.assertEqual(reservation.labels["laomedo.launch_token"].get_secret_value(),"private")
            watch.cleanup.assert_called_once_with(watch_seconds=0)

    @unittest.skipUnless(__import__("importlib.util").util.find_spec("py_docker"), "Requires optional Docker runtime")
    def test_missing_legacy_endpoint_cannot_claim_absence(self):
        identity=ContainerIdentity(name="exact",run_id="run",token="private")
        with patch("py_docker.Client") as client:
            self.assertEqual(inspect_exact(identity),("unknown",None))
            self.assertEqual(cleanup_exact(identity),(False,"unknown"))
            client.assert_not_called()

    @unittest.skipUnless(__import__("importlib.util").util.find_spec("py_docker"), "Requires optional Docker runtime")
    def test_loss_watch_delegates_configured_duration(self):
        identity=ContainerIdentity(name="exact",run_id="run",token="private",docker_endpoint="unix:///original.sock")
        with patch("py_docker.Client") as client:
            watch=client.return_value.__enter__.return_value.containers.watch.return_value
            watch.cleanup.return_value.verified=False
            watch.cleanup.return_value.detail="never_observed"
            self.assertEqual(cleanup_after_loss(identity,watch_seconds=.2),(False,"never_observed"))
            watch.cleanup.assert_called_once_with(watch_seconds=.2)

    def test_supervisor_is_detached_from_runner_group(self):
        options = _detached_process_options()
        if "creationflags" in options:
            self.assertTrue(options["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP)
            self.assertTrue(options["creationflags"] & subprocess.CREATE_BREAKAWAY_FROM_JOB)
        else:
            self.assertEqual(options, {"start_new_session": True})

    def test_eof_runs_cleanup_after_ready_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            record = root / "record.json"
            record.write_text(json.dumps({"run_id": "run-one", "container_ownership": {
                "name": "exact-name", "launch_token": "token-one"}}), encoding="utf-8")
            ready, result = root / "ready", root / "result.json"
            with patch("laomedo.host.leases.utils.sys.stdin", io.StringIO("")), \
                    patch("laomedo.host.leases.utils.cleanup_after_loss", return_value=(True, "removed")) as cleanup:
                self.assertEqual(supervise(record, "exact-name", "run-one", "token-one",
                                           ready, result), 0)
            self.assertEqual(ready.read_text(encoding="utf-8"), "token-one")
            self.assertEqual(json.loads(result.read_text(encoding="utf-8")),
                             {"reason": "eof", "cleanup_verified": True, "state": "removed"})
            cleanup.assert_called_once_with(ContainerIdentity(name='exact-name', run_id='run-one', token='token-one'))


if __name__ == "__main__":
    unittest.main()
