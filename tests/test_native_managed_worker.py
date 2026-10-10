"""No-process/no-container fixture worker checks, not campaign evidence."""
import json
from pathlib import Path
from types import SimpleNamespace
import threading
import tempfile
from unittest.mock import Mock, patch
import unittest

from experiments.exp104 import native_managed_worker as worker



class NativeManagedWorkerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="laomedo-managed-worker-test-")
        self.addCleanup(self.directory.cleanup)
        self.worker_root = Path(self.directory.name)

    def test_worker_saves_exact_owned_container_id_and_real_lease_scope(self):
        tmp_path = self.worker_root
        selected = worker.identities("a")
        record_dir = tmp_path / "runner/runs" / selected["run_id"]
        record_dir.mkdir(parents=True)
        mediator_dir = tmp_path / "host/mediator"
        mediator_dir.mkdir(parents=True)
        mediator = {"repository": worker.REPOSITORY,
            "connection_id": worker.IDENTITY + "-connection", "generation": 1,
            "port": 1234, "instance": "instance"}
        (mediator_dir / "mediator.json").write_text(json.dumps(mediator))
        lease = SimpleNamespace(grant_id="exact-grant", lost=threading.Event(),
            finish=Mock(), dir=tmp_path / "lease")
        child = Mock()
        child.poll.return_value = 0
        with patch.object(worker, "LeaseClient", return_value=lease) as registered, \
                patch.object(worker, "command", return_value=["not-executed"]), \
                patch.object(worker.subprocess, "Popen", return_value=child), \
                patch.object(worker, "inspect_exact", return_value=("owned", "d" * 64)), \
                patch.object(worker, "cleanup_exact", return_value=(True, "absent")):
            worker.run(tmp_path, "a")
        ready = json.loads((tmp_path / "a-ready.json").read_bytes())
        assert ready["container_id"] == "d" * 64
        assert ready["grant_id"] == "exact-grant"
        scope = registered.call_args.kwargs["mediation_request"]
        assert scope == {"invocation_id": selected["invocation_id"],
            "repository": worker.REPOSITORY, "branch": selected["branch"], "base_branch": "main"}
        record = json.loads((record_dir / "record.json").read_bytes())
        assert record["status"] == "completed"
        assert record["container_ownership"]["grant_id"] == "exact-grant"
        assert record["container_ownership"]["cleanup_verified"] is True
        lease.finish.assert_called_once()


    def test_worker_mounts_only_workspace_capability_and_fixed_code(self):
        tmp_path = self.worker_root
        selected = worker.identities("b")
        lease = SimpleNamespace(dir=tmp_path / "host/lease/leases/one")
        with patch.object(worker, "prepare_commands", return_value=tmp_path / "wrappers"):
            args = worker.command(tmp_path, "b", lease, {"port": 1234, "instance": "instance"})
        assert args[-4:] == [worker.GIT_IMAGE_ID, "sh", "-c", "sleep 600"]
        mounts = [args[i + 1] for i, word in enumerate(args) if word == "--mount"]
        assert len(mounts) == 6
        assert sum(",readonly" not in mount for mount in mounts) == 1
        assert not any(".env" in mount or "authority.sqlite" in mount for mount in mounts)
        assert "--env=LAOMEDO_RUN_BRANCH=" + selected["branch"] in args
