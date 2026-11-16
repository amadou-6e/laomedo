"""Synthetic saved-runner ownership and fencing checks, not native acceptance."""

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from laomedo.host.provider_connections.controllers import ProviderControllers
from laomedo.host.provider_connections.errors import ProviderConnectionError
from laomedo.host.provider_connections.models import ConnectionRecord
from laomedo.host.provider_connections.service import ProviderConnections


class FakeNativeAgent:
    """Exercise the real loopback fence while avoiding Docker and model work."""

    def __init__(self, state, store, source, **kwargs):
        self.state = state
        self.state.mkdir(parents=True)
        (self.state / "runs").mkdir()
        self.api_token = "0" * 64
        (self.state / "api-token").write_text(self.api_token, encoding="utf-8")
        self.lock = threading.Lock()
        self.provider = "codex"
        self.auth = kwargs["auth_connection"]

    def editor_model_catalog(self):
        return {"provider": "codex", "models": []}

    def start_async(self, body, **kwargs):
        record = {"run_id": str(uuid4()), "status": "prepared"}
        root = self.state / "runs" / record["run_id"]
        root.mkdir()
        (root / "record.json").write_text(json.dumps(record), encoding="utf-8")
        return record

    def status(self, run_id):
        return json.loads(
            (self.state / "runs" / run_id / "record.json").read_text(encoding="utf-8")
        )

    def cancel(self, run_id):
        record = self.status(run_id)
        record.update(status="cancelled", cancel_confirmed=True)
        (self.state / "runs" / run_id / "record.json").write_text(
            json.dumps(record), encoding="utf-8"
        )
        return record


class ProviderControllerTests(unittest.TestCase):
    """Check exact owner routing, retained epochs and cancellation inventory."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.service = ProviderConnections(root / "credentials")
        self.addCleanup(self.service.close)
        self.profile = uuid4()
        self.one, self.two = uuid4(), uuid4()
        self.records = [
            ConnectionRecord(
                connection_id=connection,
                credential_id=uuid4(),
                client_id="oaiapp_test",
                subject_hash=str(connection),
                generation=1,
                label="Account",
            )
            for connection in (self.one, self.two)
        ]
        self.service._save(self.profile, self.records)
        self.manager = ProviderControllers(
            self.service,
            root / "runs",
            root / "skills",
            root / "source",
            factory=FakeNativeAgent,
        )
        self.addCleanup(self.manager.close)

    def post(self, base, path, body):
        request = Request(
            base + path,
            data=json.dumps(body).encode(),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + "0" * 64,
            },
        )
        with urlopen(request, timeout=3) as response:
            return json.load(response)

    def test_connections_have_distinct_runners_and_foreign_profile_cannot_bind(self):
        one = self.manager.endpoint(self.profile, self.one)
        two = self.manager.endpoint(self.profile, self.two)
        self.assertNotEqual(one, two)
        with self.assertRaisesRegex(
            ProviderConnectionError, "provider_connection_unavailable"
        ):
            self.manager.endpoint(uuid4(), self.one)
        self.assertEqual(len(self.manager.slots), 2)

    def test_reconnect_refuses_old_gateway_dispatch_but_preserves_evidence(self):
        endpoint, _token = self.manager.endpoint(self.profile, self.one)
        record = self.post(endpoint, "/v1/runs/async", {"request_id": str(uuid4())})
        replaced = self.records[0].model_copy(update={"generation": 2})
        self.service._save(self.profile, [replaced, self.records[1]])
        with self.assertRaises(HTTPError) as failure:
            self.post(endpoint, "/v1/runs/async", {"request_id": str(uuid4())})
        self.assertEqual(failure.exception.code, 409)
        prior_endpoint = self.manager.endpoint(
            self.profile, self.one, run_id=record["run_id"]
        )
        self.assertEqual(prior_endpoint[0], endpoint)
        self.assertNotEqual(self.manager.endpoint(self.profile, self.one)[0], endpoint)

    def test_disconnect_inventory_revision_changes_with_new_work(self):
        endpoint, _token = self.manager.endpoint(self.profile, self.one)
        before = self.service.disconnect_info(self.profile, self.one)
        record = self.post(endpoint, "/v1/runs/async", {"request_id": str(uuid4())})
        after = self.service.disconnect_info(self.profile, self.one)
        self.assertEqual(after.active_runs, 1)
        self.assertGreater(after.revision, before.revision)
        with self.assertRaisesRegex(
            ProviderConnectionError, "provider_confirmation_changed"
        ):
            self.service.disconnect(
                self.profile, self.one, before.generation, before.revision
            )
        self.assertFalse(self.manager.stop(self.profile, self.one))
        self.assertTrue(self.manager.stop(self.profile, self.one))
        slot = self.manager.slots[(self.profile, self.one, 1)]
        self.assertEqual(slot.runner.status(record["run_id"])["status"], "cancelled")
