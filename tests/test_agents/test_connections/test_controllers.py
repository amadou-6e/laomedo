"""Synthetic saved-runner ownership and fencing checks, not native acceptance."""

import json
from importlib.util import find_spec
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4
from unittest.mock import Mock, patch
from types import SimpleNamespace

from laomedo.agents.connections.controllers import ProviderControllers
from laomedo.agents.connections.errors import ProviderConnectionError
from laomedo.agents.connections.models import ConnectionRecord
from laomedo.agents.connections.service import ProviderConnections
from laomedo.agents.errors import RunnerError
from laomedo.agents.workspaces.models import WorkspaceChanges
from laomedo.docker import DockerRuntime


class FakeNativeAgent:
    """Exercise the real loopback fence while avoiding Docker and model work."""

    def __init__(self, state, store, source, **kwargs):
        self.state = state
        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / "runs").mkdir(exist_ok=True)
        self.api_token = "0" * 64
        (self.state / "api-token").write_text(self.api_token, encoding="utf-8")
        self.lock = threading.Lock()
        self.provider = "codex"
        self.auth = kwargs["auth_connection"]
        self.pending = []

    def has_live_session(self, run_id):
        return False

    def close(self):
        return None

    def pending_resumes(self):
        return list(self.pending)

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

    def test_assistant_has_distinct_source_and_graph_cannot_resolve_its_run(self):
        graph = self.manager.endpoint(self.profile, self.one)
        assistant = self.manager.assistant_endpoint(self.profile, self.one, 1)
        self.assertNotEqual(graph, assistant)
        record = self.post(assistant[0], "/v1/runs/async", {"task": "fixture"})
        with self.assertRaises(ProviderConnectionError):
            self.manager.connection_for_run(self.profile, record["run_id"])
        with self.assertRaises(ProviderConnectionError):
            self.manager.endpoint(self.profile, self.one, run_id=record["run_id"])
        self.assertEqual(
            self.manager.connection_for_run(
                self.profile, record["run_id"], scope="assistant"
            ),
            self.one,
        )
        self.assertEqual(self.manager.inventory(self.profile, self.one)[0], 1)
        self.assertFalse(self.manager.stop(self.profile, self.one))
        slot = self.manager.slots[(self.profile, self.one, 1, "assistant")]
        self.assertEqual(slot.runner.status(record["run_id"])["status"], "cancelled")
        self.assertTrue(self.manager.stop(self.profile, self.one))
        with self.assertRaises(ProviderConnectionError):
            self.manager.assistant_endpoint(self.profile, self.one, 2)
        with self.assertRaises(ProviderConnectionError):
            self.manager.assistant_endpoint(uuid4(), self.one, 1)

    def test_workspace_changes_are_fenced_to_owner_and_connection_generation(self):
        endpoint = self.manager.endpoint(self.profile, self.one)
        record = self.post(endpoint[0], "/v1/runs/async", {"task": "fixture"})
        slot = self.manager.slots[(self.profile, self.one, 1, "graph")]
        projection = WorkspaceChanges(
            run_id=record["run_id"],
            source_hash="source",
            post_run_hash="after",
            patch_hash="patch",
            patch="content",
        )
        slot.runner.workspace_changes = Mock(return_value=projection)
        value = self.manager.workspace_changes(self.profile, record["run_id"])
        self.assertEqual(value.connection_id, self.one)
        self.assertEqual(value.generation, 1)
        self.assertEqual(value.changes, projection)
        self.assertEqual(slot.operations, 0)
        with self.assertRaises(ProviderConnectionError):
            self.manager.workspace_changes(uuid4(), record["run_id"])
        self.records[0] = self.records[0].model_copy(update={"generation": 2})
        self.service._save(self.profile, self.records)
        with self.assertRaises(ProviderConnectionError):
            self.manager.workspace_changes(self.profile, record["run_id"])
        self.assertEqual(slot.operations, 0)

    def test_restart_recovers_assistant_scope_without_a_graph_controller(self):
        self.manager.assistant_endpoint(self.profile, self.one, 1)
        self.manager.close()
        replacement = ProviderControllers(
            self.service,
            self.manager.root,
            self.manager.skill_store,
            self.manager.source,
            factory=FakeNativeAgent,
        )
        self.addCleanup(replacement.close)
        replacement.recover()
        slot = replacement.slots[(self.profile, self.one, 1, "assistant")]
        self.assertEqual(slot.scope, "assistant")
        self.assertEqual(slot.state.name, "state")
        self.assertTrue(
            (slot.state.parent / "source" / "workspace" / "README.md").is_file()
        )

    def test_claude_assistant_does_not_pin_execution_to_the_login_image(self):
        self.records[0] = self.records[0].model_copy(update={"provider": "claude"})
        self.service._save(self.profile, self.records)
        self.manager.factory = None
        native = SimpleNamespace(name="laomedo-claude-fixture", image_id="sha256:login")
        with (
            patch.object(self.service.claude, "profile", return_value=native),
            patch(
                "laomedo.agents.connections.controllers.AgentProviderRegistry.create_agent"
            ) as create,
        ):
            create.side_effect = lambda provider, *args, **kwargs: FakeNativeAgent(
                *args, **kwargs
            )
            self.manager._create(
                self.profile, self.one, 1, recovery=True, scope="assistant"
            )
            self.assertNotIn("image", create.call_args.kwargs)
            self.assertEqual(create.call_args.kwargs["profile_volume"], native.name)
            self.manager._create(
                self.profile, self.one, 1, recovery=True, scope="graph"
            )
            self.assertEqual(create.call_args.kwargs["image"], native.image_id)

    def test_shutdown_closes_remaining_accounts_after_one_runner_fails(self):
        self.manager.assistant_endpoint(self.profile, self.one, 1)
        self.manager.assistant_endpoint(self.profile, self.two, 1)
        slots = list(self.manager.slots.values())
        slots[0].runner.close = Mock(side_effect=RuntimeError("cleanup uncertain"))
        slots[1].runner.close = Mock()
        servers = [slot.server for slot in slots]
        with self.assertRaises(ProviderConnectionError) as failure:
            self.manager.close()
        self.assertEqual(failure.exception.code, "provider_cleanup_unconfirmed")
        slots[1].runner.close.assert_called_once()
        self.assertTrue(all(server.fileno() == -1 for server in servers))
        self.assertIsNot(ProviderControllers._current, self.manager)
        slots[0].runner.close = Mock()

    def test_connections_have_distinct_runners_and_foreign_profile_cannot_bind(self):
        one = self.manager.endpoint(self.profile, self.one)
        two = self.manager.endpoint(self.profile, self.two)
        self.assertNotEqual(one, two)
        with self.assertRaisesRegex(
            ProviderConnectionError, "provider_connection_unavailable"
        ):
            self.manager.endpoint(uuid4(), self.one)
        self.assertEqual(len(self.manager.slots), 2)

    def test_failed_native_startup_can_be_retried_without_restarting_the_app(self):
        """A failed Docker prerequisite never strands dispatch and local removal."""
        self.manager.factory = Mock(
            side_effect=[OSError("Docker unavailable"), FakeNativeAgent]
        )
        with self.assertRaises(OSError):
            self.manager.endpoint(self.profile, self.one)
        self.manager.factory = FakeNativeAgent
        endpoint, _token = self.manager.endpoint(self.profile, self.one)
        self.assertTrue(endpoint.startswith("http://127.0.0.1:"))
        self.assertTrue(self.manager.stop(self.profile, self.one))

    def test_trailing_slash_routes_use_the_same_admission_fence(self):
        """Every path accepted by the base handler is counted and fenced identically."""
        endpoint, _token = self.manager.endpoint(self.profile, self.one)
        slot = self.manager.slots[(self.profile, self.one, 1, "graph")]
        self.service._save(
            self.profile,
            [
                self.records[0].model_copy(update={"lifecycle": "disconnecting"}),
                self.records[1],
            ],
        )
        for path in (
            "/v1/runs/",
            "/v1/runs/async/",
            "/v1/runs/" + str(uuid4()) + "/resume/",
            "/v1/runs/" + str(uuid4()) + "/resume/async",
            "/v1/runs/" + str(uuid4()) + "/resume/async/",
        ):
            with self.assertRaises(HTTPError) as failure:
                self.post(endpoint, path, {"request_id": str(uuid4())})
            self.assertEqual(failure.exception.code, 409)
            self.assertEqual(
                json.load(failure.exception)["error_category"],
                "provider_connection_disconnecting",
            )
        self.assertEqual(slot.operations, 0)
        self.assertEqual(self.manager._records(slot), [])

    def test_catalog_and_native_work_cannot_overlap_credential_rotation(self):
        self.manager.endpoint(self.profile, self.one)
        slot = self.manager.slots[(self.profile, self.one, 1, "graph")]
        self.manager.admit_operation(slot, catalog=True)
        with self.assertRaisesRegex(
            ProviderConnectionError, "provider_connection_busy"
        ):
            self.manager.admit_operation(slot)
        slot.operations = slot.catalog_operations = 0
        self.manager.admit_operation(slot)
        with self.assertRaisesRegex(
            ProviderConnectionError, "provider_connection_busy"
        ):
            self.manager.admit_operation(slot, catalog=True)
        slot.operations = 0

    def test_corrupt_inventory_refuses_catalog_with_a_safe_response(self):
        endpoint, _token = self.manager.endpoint(self.profile, self.one)
        slot = self.manager.slots[(self.profile, self.one, 1, "graph")]
        record = slot.state / "runs" / str(uuid4()) / "record.json"
        record.parent.mkdir()
        record.write_text("{", encoding="utf-8")
        request = Request(
            endpoint + "/v1/models", headers={"Authorization": "Bearer " + "0" * 64}
        )
        try:
            with self.assertRaises(HTTPError) as failure:
                urlopen(request, timeout=3)
            self.assertEqual(failure.exception.code, 409)
            self.assertEqual(
                json.load(failure.exception)["error_category"],
                "provider_runner_unavailable",
            )
            self.assertEqual(slot.operations, 0)
        finally:
            record.unlink()

    def test_gateway_preserves_safe_underlying_failure_diagnostics(self):
        endpoint, _token = self.manager.endpoint(self.profile, self.one)
        for error, expected in (
            (
                PermissionError(13, "private path"),
                {"failure_kind": "os_error", "errno": 13},
            ),
            (
                RunnerError("resume_journal_unavailable"),
                {
                    "failure_kind": "domain_error",
                    "runner_code": "resume_journal_unavailable",
                },
            ),
        ):
            with (
                self.subTest(error=type(error).__name__),
                unittest.mock.patch.object(
                    self.manager, "admit_operation", side_effect=error
                ),
            ):
                with self.assertRaises(HTTPError) as failure:
                    self.post(endpoint, "/v1/runs/async", {})
                with failure.exception as response:
                    value = json.load(response)
                self.assertEqual(value["error_category"], "provider_runner_unavailable")
                for key, wanted in expected.items():
                    self.assertEqual(value["runner_diagnostics"][key], wanted)
                self.assertNotIn("private", json.dumps(value))

    def test_cleanup_waits_if_failed_slot_retry_is_already_starting(self):
        self.manager.endpoint(self.profile, self.one)
        slot = self.manager.slots[(self.profile, self.one, 1, "graph")]
        starting = slot.model_copy(
            update={"runner": None, "server": None, "creating": True}
        )
        self.manager.slots[(self.profile, self.one, 1, "graph")] = slot.model_copy(
            update={"runner": None, "server": None}
        )
        with unittest.mock.patch.object(self.manager, "_create", return_value=starting):
            self.assertFalse(self.manager.stop(self.profile, self.one))
        self.manager.slots[(self.profile, self.one, 1, "graph")] = slot

    @unittest.skipUnless(find_spec("py_docker"), "Requires the optional Docker SDK")
    def test_native_recovery_failure_retains_slot_and_allows_later_retry(self):
        """Daemon failure does not abort app startup or discard exact owned state."""
        from py_docker.errors import DockerOperationError

        state = self.manager.root / str(self.profile) / str(self.one) / "g1"
        state.mkdir(parents=True)
        factory = self.manager.factory
        self.manager.factory = Mock(side_effect=DockerOperationError("daemon offline"))
        self.manager.recover()
        slot = self.manager.slots[(self.profile, self.one, 1, "graph")]
        self.assertIsNone(slot.runner)
        self.assertFalse(slot.creating)
        with self.assertRaisesRegex(
            ProviderConnectionError, "provider_cleanup_unconfirmed"
        ):
            self.manager.stop(self.profile, self.one)
        self.manager.factory = factory
        self.assertTrue(self.manager.stop(self.profile, self.one))

    @unittest.skipUnless(find_spec("py_docker"), "Requires the optional Docker SDK")
    def test_native_receipt_failure_settles_cleanup_as_retryable(self):
        """Existing Claude/OpenCode slots keep native custody on recovery errors."""
        from py_docker.errors import DockerOperationError

        self.manager.endpoint(self.profile, self.one)
        slot = self.manager.slots[(self.profile, self.one, 1, "graph")]
        receipt = slot.state / "receipts" / "owned.json"
        receipt.parent.mkdir()
        receipt.write_text("owned fixture")
        for provider in ("claude", "opencode"):
            with self.subTest(provider=provider):
                runner = Mock(provider=provider)
                runner.pending_resumes.return_value = []
                runner.lock = threading.Lock()
                runner.container.client.side_effect = DockerOperationError(
                    "daemon offline"
                )
                self.manager.slots[(self.profile, self.one, 1, "graph")] = (
                    slot.model_copy(update={"runner": runner})
                )
                with unittest.mock.patch.object(
                    DockerRuntime,
                    "recover_receipts",
                    side_effect=DockerOperationError("daemon offline"),
                ):
                    runner._recover_containers.side_effect = DockerOperationError(
                        "daemon offline"
                    )
                    self.service._save(
                        self.profile,
                        [
                            (
                                row.model_copy(update={"lifecycle": "disconnecting"})
                                if row.connection_id == self.one
                                else row
                            )
                            for row in self.records
                        ],
                    )
                    result = self.service.retry_cleanup(self.profile, self.one)
                self.assertEqual(result.status, "cleanup_required")
                self.assertTrue(receipt.exists())
        self.manager.slots[(self.profile, self.one, 1, "graph")] = slot

    def test_unavailable_recovered_runner_keeps_settings_and_cleanup_retryable(self):
        state = self.manager.root / str(self.profile) / str(self.one) / "g1"
        state.mkdir(parents=True)
        self.manager.source = None
        self.manager.recover()
        slot = self.manager.slots[(self.profile, self.one, 1, "graph")]
        self.assertFalse(slot.creating)
        self.assertIsNone(slot.runner)
        with self.assertRaisesRegex(
            ProviderConnectionError, "provider_cleanup_unconfirmed"
        ):
            self.manager.stop(self.profile, self.one)
        self.manager.source = state.parent
        self.assertTrue(self.manager.stop(self.profile, self.one))

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
        slot = self.manager.slots[(self.profile, self.one, 1, "graph")]
        self.assertEqual(slot.runner.status(record["run_id"])["status"], "cancelled")

    def test_queued_resume_is_counted_and_cleanup_waits_for_settlement(self):
        endpoint, _token = self.manager.endpoint(self.profile, self.one)
        record = self.post(endpoint, "/v1/runs/async", {"request_id": str(uuid4())})
        slot = self.manager.slots[(self.profile, self.one, 1, "graph")]
        record["status"] = "completed"
        (slot.state / "runs" / record["run_id"] / "record.json").write_text(
            json.dumps(record), encoding="utf-8"
        )
        slot.runner.pending = [{"run_id": record["run_id"], "status": "reserved"}]
        self.assertEqual(self.manager.inventory(self.profile, self.one)[0], 1)
        with self.assertRaisesRegex(
            ProviderConnectionError, "provider_connection_busy"
        ):
            self.manager.admit_operation(slot, catalog=True)
        self.assertFalse(self.manager.stop(self.profile, self.one))
        slot.runner.pending = []
        self.assertTrue(self.manager.stop(self.profile, self.one))

    def test_retained_credential_facade_cannot_borrow_after_controller_close(self):
        from laomedo.host.credentials.siwc.errors import AuthError

        self.manager.endpoint(self.profile, self.one)
        slot = self.manager.slots[(self.profile, self.one, 1, "graph")]
        self.manager.closed = True
        with unittest.mock.patch.object(self.service, "borrow") as borrow:
            with self.assertRaisesRegex(AuthError, "auth_revoked"):
                slot.runner.auth.access_token("oaiapp_test")
            with self.assertRaisesRegex(AuthError, "auth_revoked"):
                slot.runner.auth.account("oaiapp_test")
            borrow.assert_not_called()

    def test_unknown_resume_does_not_skip_cancellation_in_other_generations(self):
        endpoint, _token = self.manager.endpoint(self.profile, self.one)
        first = self.post(endpoint, "/v1/runs/async", {"request_id": str(uuid4())})
        old_slot = self.manager.slots[(self.profile, self.one, 1, "graph")]
        old_slot.runner.pending = [{"run_id": first["run_id"], "status": "unknown"}]
        self.service._save(
            self.profile,
            [self.records[0].model_copy(update={"generation": 2}), self.records[1]],
        )
        endpoint, _token = self.manager.endpoint(self.profile, self.one)
        second = self.post(endpoint, "/v1/runs/async", {"request_id": str(uuid4())})
        new_slot = self.manager.slots[(self.profile, self.one, 2, "graph")]
        with self.assertRaisesRegex(
            ProviderConnectionError, "provider_cleanup_unconfirmed"
        ):
            self.manager.stop(self.profile, self.one)
        self.assertEqual(old_slot.runner.status(first["run_id"])["status"], "cancelled")
        self.assertEqual(
            new_slot.runner.status(second["run_id"])["status"], "cancelled"
        )

    def test_unknown_resume_exposes_cleanup_retry_without_erasing_credentials(self):
        self.manager.endpoint(self.profile, self.one)
        slot = self.manager.slots[(self.profile, self.one, 1, "graph")]
        slot.runner.pending = [{"run_id": str(uuid4()), "status": "unknown"}]
        self.service._save(
            self.profile,
            [
                self.records[0].model_copy(update={"lifecycle": "disconnecting"}),
                self.records[1],
            ],
        )
        with unittest.mock.patch.object(self.service.codex, "_scrub") as scrub:
            result = self.service.retry_cleanup(self.profile, self.one)
            self.assertEqual(result.status, "cleanup_required")
            self.assertEqual(
                self.service._record(self.profile, self.one).lifecycle,
                "cleanup_required",
            )
            scrub.assert_not_called()
