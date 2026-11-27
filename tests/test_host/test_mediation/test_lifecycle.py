"""Internal production-API composition controls, never deployment acceptance."""

from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener
from uuid import uuid4

from laomedo.host.leases.models import ContainerIdentity
from laomedo.host.leases.service import LeaseService
from laomedo.host.mediation.authority import RunGrantAuthority
from laomedo.host.mediation.service import MediationHTTPService
from laomedo.host.mediation.store import MediationStore


class MediationLifecycleTests(unittest.TestCase):
    def test_approval_binding_http_read_and_done_revoke_exact_grant(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = MediationStore(root / "mediator.sqlite")
            authority = RunGrantAuthority(root / "authority.sqlite")
            lease = LeaseService(
                root / "leases",
                mediator=store,
                mediation_authority=authority.authorize_lease,
            )
            self.addCleanup(lease.server.server_close)
            transport = Mock(return_value={"internal": True})
            mediator = MediationHTTPService(store, transport)
            thread = threading.Thread(target=mediator.serve, daemon=True)
            thread.start()
            try:
                run_id = str(uuid4())
                reference = authority.approve(
                    invocation_id="invocation-" + run_id,
                    repository="example/disposable",
                    branch="branch-" + run_id,
                    operations={"actions_read"},
                    reviewed_by="internal-control",
                )
                scope = authority.bind_run(reference, run_id)
                identity = ContainerIdentity(
                    name="laomedo-internal-" + run_id,
                    run_id=run_id,
                    token=uuid4().hex,
                    docker_endpoint="unix:///internal-unused.sock",
                )
                directory = lease.state / "leases" / identity.token.get_secret_value()
                directory.mkdir()
                (directory / "heartbeat").write_text(repr(time.time()))
                (directory / "heartbeat.monotonic").write_text(repr(time.monotonic()))
                (directory / "lease.json").write_text(
                    json.dumps(
                        identity.registration(
                            runner_pid=os.getpid(),
                            created_at=time.time(),
                            mediation=scope,
                        )
                    )
                )
                lease.tick()
                accepted = json.loads((directory / "accepted.json").read_text())
                token = (directory / "grant.secret").read_text()
                body = json.dumps(
                    {
                        "repository": "example/disposable",
                        "operation": "actions_read",
                        "payload": {"resource": "runs"},
                    }
                ).encode()
                request = Request(
                    f"http://127.0.0.1:{mediator.port}/v1/mediate",
                    data=body,
                    method="POST",
                    headers={
                        "Authorization": "Bearer " + token,
                        "Content-Type": "application/json",
                        "X-Laomedo-Mediator-Instance": mediator.instance,
                    },
                )
                opener = build_opener(ProxyHandler({}))
                with opener.open(request, timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(json.load(response)["state"], "confirmed")
                transport.assert_called_once_with(
                    "example/disposable", "actions_read", {"resource": "runs"}
                )
                (directory / "done").touch()
                with patch(
                    "laomedo.host.leases.service.inspect_exact",
                    return_value=("absent", None),
                ) as inspect:
                    lease.tick()
                    deadline = time.monotonic() + 5
                    while (
                        not (directory / "result.json").is_file()
                        and time.monotonic() < deadline
                    ):
                        time.sleep(0.01)
                    result = json.loads((directory / "result.json").read_text())
                self.assertEqual(result["reason"], "done")
                self.assertTrue(result["cleanup_verified"])
                self.assertEqual(result["revoked_grants"], [accepted["grant_id"]])
                inspect.assert_called_once()
                observed = inspect.call_args.args[0]
                self.assertEqual(
                    (observed.name, observed.run_id, observed.docker_endpoint),
                    (identity.name, identity.run_id, identity.docker_endpoint),
                )
                with self.assertRaises(HTTPError) as denied:
                    opener.open(request, timeout=5)
                self.assertEqual(denied.exception.code, 403)
                denied.exception.close()
                self.assertEqual(transport.call_count, 1)
                self.assertFalse(store.renew_grant(accepted["grant_id"], 60))
            finally:
                mediator.close()
                thread.join(5)
                self.assertFalse(
                    thread.is_alive(), "Owned mediation listener did not stop"
                )

    def test_repeated_revocation_is_durable_and_unknown_grants_never_renew(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = MediationStore(Path(temporary) / "mediator.sqlite")
            grant, _ = store.issue(
                run_id="internal-run",
                invocation_id="internal-invocation",
                repository="example/disposable",
                operations={"issue_list"},
                ttl_seconds=60,
            )
            self.assertEqual(store.revoke_run("internal-run"), 1)
            for _ in range(2):
                self.assertEqual(store.revoke_run("internal-run"), 0)
                self.assertFalse(store.renew_grant(grant, 60))
                with closing(sqlite3.connect(store.path)) as db:
                    self.assertIsNotNone(
                        db.execute(
                            "SELECT revoked_at FROM grants WHERE grant_id=?", (grant,)
                        ).fetchone()[0]
                    )
            self.assertEqual(store.revoke_run("unknown-run"), 0)
            self.assertFalse(store.renew_grant("unknown-grant", 60))
