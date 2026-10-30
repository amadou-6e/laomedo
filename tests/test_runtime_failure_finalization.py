"""Internal producer and finalization controls; no native or Docker dispatch."""

from importlib.util import find_spec
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

if find_spec("py_docker"):
    from py_docker.errors import (
        CleanupUnconfirmedError,
        DockerOperationError,
        ReceiptInUseError,
    )
    from py_docker.containers.models import ContainerSpec

import test_local_runner as fixtures
import test_opencode_runner as opencode_fixtures
from laomedo.agents.agents.base.utils import failure_observation
from laomedo.agents.agents.codex.controller.models import CodexTurn
from laomedo.agents.agents.codex.controller.service import CodexController
from laomedo.agents.agents.opencode.boundary import IsolatedOpenCode
from laomedo.agents.errors import RunnerError


@unittest.skipUnless(find_spec("py_docker"), "Requires the optional runner SDK")
class OpenCodeReceiptTests(unittest.TestCase):
    """Call actual boundary methods with owned receipt and SDK failure controls."""

    def make_backend(self, directory):
        backend = IsolatedOpenCode.__new__(IsolatedOpenCode)
        backend.receipts = Path(directory)
        backend.allocated_receipts = set()
        backend.docker = Mock()
        backend.broker = backend.session = None
        backend.closing = backend.termination_verified = False
        backend.cleanup_observed = None
        return backend

    def test_catalogue_cleanup_failure_keeps_primary_and_registers_before_dispatch(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            backend = self.make_backend(directory)
            backend.check_auth_fresh = Mock()
            backend.image_id = "sha256:" + "a" * 64
            backend.spec = ContainerSpec(
                image=backend.image_id, name="internal-catalog"
            )
            error = CleanupUnconfirmedError(
                "confirm owned container cleanup",
                primary=DockerOperationError("create container"),
            )
            backend.docker.jobs.run.side_effect = error
            with self.assertRaisesRegex(
                RunnerError, "opencode_container_cleanup_unverified"
            ) as raised:
                backend.models()
            job = backend.docker.jobs.run.call_args.args[0]
            self.assertIn(job.receipt_path, backend.allocated_receipts)
            self.assertEqual(
                raised.exception.observation.primary_operation, "create container"
            )
            self.assertEqual(
                raised.exception.observation.sdk_code, "docker_cleanup_unconfirmed"
            )
            backend.close()
            backend.docker.sessions.recover.assert_called_once_with(job.receipt_path)
            self.assertTrue(backend.cleanup_observed)

    def test_close_drains_before_exact_recovery_and_leaves_unrelated_receipt_alone(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            backend = self.make_backend(directory)
            catalog, worker, unrelated = [
                Path(directory) / name
                for name in ("catalog.json", "worker.json", "unrelated.json")
            ]
            unrelated.write_text("unrelated", encoding="utf-8")
            backend.allocated_receipts.add(catalog)
            backend.broker = SimpleNamespace(
                stop=Mock(),
                close=Mock(),
                lock=threading.Lock(),
                allocated_receipts={worker},
                drained=False,
            )
            order = []
            backend.broker.stop.side_effect = lambda: order.append("stop")
            backend.broker.close.side_effect = lambda: order.append("drain")
            backend.docker.sessions.recover.side_effect = lambda receipt: order.append(
                receipt
            )
            backend.close()
            self.assertEqual(order[:2], ["stop", "drain"])
            self.assertEqual(set(order[2:]), {catalog, worker})
            self.assertEqual(unrelated.read_text(), "unrelated")
            self.assertTrue(backend.termination_verified)

    def test_pending_or_undrained_resources_cannot_confirm_cleanup(self):
        for phase in ("recover", "drain", "partial"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                backend = self.make_backend(directory)
                docker = backend.docker
                backend.allocated_receipts.add(Path(directory) / "catalog.json")
                if phase == "recover":
                    docker.sessions.recover.side_effect = ReceiptInUseError(
                        "acquire owned receipt"
                    )
                elif phase == "drain":
                    backend.broker = SimpleNamespace(
                        stop=Mock(),
                        close=Mock(
                            side_effect=RunnerError(
                                "opencode_container_cleanup_unverified"
                            )
                        ),
                        lock=threading.Lock(),
                        allocated_receipts=set(),
                        drained=False,
                    )
                else:
                    backend.docker = None
                with self.assertRaisesRegex(
                    RunnerError, "opencode_container_cleanup_unverified"
                ):
                    backend.close()
                self.assertFalse(backend.termination_verified)
                self.assertFalse(backend.cleanup_observed)
                if phase != "recover":
                    docker.sessions.recover.assert_not_called()
                if phase != "partial":
                    docker.close.assert_called_once()

    def test_stop_failure_still_attempts_session_broker_and_client_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            backend = self.make_backend(directory)
            backend.session = Mock()
            backend.broker = SimpleNamespace(
                stop=Mock(side_effect=RuntimeError("PRIVATE")),
                close=Mock(),
                lock=threading.Lock(),
                allocated_receipts=set(),
            )
            with self.assertRaisesRegex(
                RunnerError, "opencode_container_cleanup_unverified"
            ):
                backend.close()
            backend.session.close.assert_called_once()
            backend.broker.close.assert_called_once()
            backend.docker.close.assert_called_once()
            self.assertFalse(backend.termination_verified)


@unittest.skipUnless(find_spec("py_docker"), "Requires the optional runner SDK")
class CodexFailureFinalizationTests(unittest.TestCase):
    """Exercise the actual agent's early returns and independent cleanup result."""

    def setUp(self):
        fixtures.LocalRunnerTests.setUp(self)

    def request(self):
        return fixtures.LocalRunnerTests.request(self)

    def make_lease(self):
        directory = self.runner.state / "internal-lease"
        directory.mkdir(exist_ok=True)
        lease = SimpleNamespace(
            instance="internal",
            grant_id="internal",
            dir=directory,
            lost=threading.Event(),
            loss=None,
            result=None,
            finish=Mock(),
        )
        self.runner.supervise_containers = True
        self.runner.lease_service = directory
        return lease

    def diagnostic(self, record):
        directory = self.runner._run_dir(record["run_id"])
        return json.loads(
            (
                directory / "diagnostics" / (record["activity_attempt_id"] + ".json")
            ).read_text()
        )

    def test_all_cancellation_returns_record_supervision_loss_not_user_cause(self):
        for phase in ("models", "open", "reserve", "native"):
            with self.subTest(phase=phase):
                lease = self.make_lease()

                def lose():
                    lease.lost.set()
                    next(iter(self.runner.cancel_flags.values())).set()

                async def models(server):
                    if phase == "models":
                        lose()
                    return [{"id": "test-model", "efforts": ["low"]}]

                async def opened(server, record, *, resume):
                    if phase == "open":
                        lose()
                    return "native-thread"

                def reserved():
                    if phase == "reserve":
                        lose()
                    return 1

                async def prompt(server, *args, **kwargs):
                    lose()
                    return CodexTurn(
                        turn_id="internal-turn",
                        status="cancelled",
                        error="cancelled_by_user",
                    )

                with (
                    patch(
                        "laomedo.agents.agents.codex.agent.LeaseClient",
                        return_value=lease,
                    ),
                    patch.object(fixtures.FakeServer, "models", models),
                    patch.object(fixtures.FakeServer, "open", opened),
                    patch.object(fixtures.FakeServer, "prompt", prompt),
                    patch.object(self.runner, "_reserve_turn", reserved),
                    patch(
                        "laomedo.agents.agents.codex.agent.cleanup_exact",
                        return_value=(True, "absent"),
                    ),
                ):
                    record = self.runner.start(self.request())
                value = self.diagnostic(record)
                self.assertEqual(value["primary"]["code"], "lease_service_lost")
                self.assertIsNone(value["cleanup_verified"])
                self.assertNotIn("diagnostics", record)
                self.assertFalse(self.runner.lock.locked())

    def test_first_sdk_error_survives_later_lease_failure_and_true_cleanup_fact(self):
        lease = self.make_lease()
        primary = failure_observation(
            DockerOperationError("create container"),
            stage="startup",
            code="runner_transport_failed",
        )

        def failed_finish():
            lease.lost.set()
            lease.result = {
                "reason": "done",
                "state": "absent",
                "cleanup_verified": True,
            }
            raise RuntimeError("lease_service_unverified")

        lease.finish.side_effect = failed_finish
        with (
            patch("laomedo.agents.agents.codex.agent.LeaseClient", return_value=lease),
            patch.object(
                self.runner,
                "_open_server",
                side_effect=RunnerError("runner_transport_failed", observation=primary),
            ),
            patch(
                "laomedo.agents.agents.codex.agent.cleanup_exact",
                return_value=(True, "absent"),
            ),
        ):
            record = self.runner.start(self.request())
        value = self.diagnostic(record)
        self.assertEqual(value["primary"]["operation"], "create container")
        self.assertEqual(value["primary"]["code"], "runner_transport_failed")
        self.assertEqual(value["cleanup"]["code"], "lease_service_unverified")
        self.assertEqual(value["cleanup_source"], "lease_result")
        self.assertTrue(value["cleanup_verified"])
        self.assertEqual(record["error_category"], "container_termination_unverified")
        self.assertFalse(record["container_ownership"]["cleanup_verified"])

    def test_none_finish_result_does_not_invent_cleanup_and_sidecar_failure_releases_lock(
        self,
    ):
        lease = self.make_lease()
        lease.finish.side_effect = RuntimeError("lease_service_unverified")
        with (
            patch("laomedo.agents.agents.codex.agent.LeaseClient", return_value=lease),
            patch.object(
                self.runner,
                "_open_server",
                side_effect=RunnerError("runner_transport_failed"),
            ),
            patch(
                "laomedo.agents.agents.codex.agent.cleanup_exact",
                return_value=(True, "absent"),
            ),
        ):
            record = self.runner.start(self.request())
        value = self.diagnostic(record)
        self.assertIsNone(value["cleanup_source"])
        self.assertIsNone(value["cleanup_verified"])
        with (
            patch.object(
                self.runner,
                "_open_server",
                side_effect=RunnerError("runner_transport_failed"),
            ),
            patch("laomedo.agents.agents.codex.agent.LeaseClient", return_value=lease),
            patch(
                "laomedo.agents.agents.codex.agent.cleanup_exact",
                return_value=(True, "absent"),
            ),
            patch(
                "laomedo.agents.agents.codex.agent.AttemptFailureRecord",
                side_effect=RuntimeError("diagnostic validation"),
            ),
        ):
            again = self.runner.start(self.request())
        self.assertEqual(again["error_category"], "container_termination_unverified")
        self.assertFalse(self.runner.lock.locked())

    def test_record_write_failure_still_attempts_sidecar_and_releases_lock(self):
        written = []
        original = __import__(
            "laomedo.agents.agents.codex.agent", fromlist=["_json"]
        )._json

        def write(path, value):
            if path.name == "record.json" and value.get("attempt_finished"):
                raise PermissionError("PRIVATE_PATH")
            return original(path, value)

        with (
            patch.object(
                self.runner,
                "_open_server",
                side_effect=RunnerError("runner_transport_failed"),
            ),
            patch("laomedo.agents.agents.codex.agent._json", side_effect=write),
            patch(
                "laomedo.agents.agents.codex.agent.write_attempt_failure",
                side_effect=lambda *args: written.append(args),
            ),
        ):
            with self.assertRaises(PermissionError):
                self.runner.start(self.request())
        self.assertEqual(len(written), 1)
        self.assertEqual(written[0][2].primary.code, "runner_transport_failed")
        self.assertFalse(self.runner.lock.locked())
        self.assertEqual(self.runner.cancel_flags, {})


@unittest.skipUnless(find_spec("py_docker"), "Requires the optional runner SDK")
class CodexControllerFailureTests(unittest.IsolatedAsyncioTestCase):
    """Cleanup keeps the first safe error while preserving public category priority."""

    async def test_close_keeps_acp_error_when_executor_cleanup_also_fails(self):
        controller = CodexController.__new__(CodexController)
        controller._closed = False
        controller.acp = SimpleNamespace(
            close=AsyncMock(side_effect=DockerOperationError("read container stream"))
        )
        controller.session = Mock()
        controller.cleanup_confirmed = False
        controller.executor = SimpleNamespace(
            close=Mock(side_effect=RunnerError("executor_termination_unverified"))
        )
        controller.logs, controller.telemetry, controller.client = [], None, Mock()
        with self.assertRaisesRegex(
            RunnerError, "executor_termination_unverified"
        ) as raised:
            await controller.close()
        self.assertEqual(
            raised.exception.observation.sdk_code, "docker_operation_failed"
        )
        controller.client.close.assert_called_once()


@unittest.skipUnless(find_spec("py_docker"), "Requires the optional runner SDK")
class OpenCodeFailureFinalizationTests(unittest.TestCase):
    """Keep standalone catalogue failure separate from actual attempted runs."""

    def setUp(self):
        opencode_fixtures.OpenCodeTests.setUp(self)

    def test_standalone_discovery_keeps_safe_primary_without_inventing_attempt_store(
        self,
    ):
        primary = failure_observation(
            DockerOperationError("create container"),
            stage="startup",
            code="opencode_controller_startup_failed",
        )

        def failed_close(backend):
            backend.log.close()
            raise RunnerError("opencode_container_cleanup_unverified")

        with (
            patch.object(
                opencode_fixtures.Backend,
                "models",
                side_effect=RunnerError(
                    "opencode_controller_startup_failed", observation=primary
                ),
            ),
            patch.object(opencode_fixtures.Backend, "close", failed_close),
        ):
            with self.assertRaisesRegex(
                RunnerError, "opencode_container_cleanup_unverified"
            ) as raised:
                self.runner.model_catalog()
        self.assertEqual(raised.exception.observation.operation, "create container")
        self.assertFalse(list(self.runner.state.glob("runs/*/diagnostics")))
        self.assertFalse(self.runner.lock.locked())

    def test_primary_survives_cleanup_failure_and_unknown_fact_is_not_confirmed(self):
        primary = failure_observation(
            DockerOperationError("create container"),
            stage="startup",
            code="opencode_controller_startup_failed",
        )

        def failed_close(backend):
            backend.log.close()
            raise RunnerError("opencode_container_cleanup_unverified")

        with (
            patch.object(
                opencode_fixtures.Backend,
                "models",
                side_effect=RunnerError(
                    "opencode_controller_startup_failed", observation=primary
                ),
            ),
            patch.object(opencode_fixtures.Backend, "close", failed_close),
        ):
            record = self.runner.start(self.payload)
        root = self.runner._run_dir(record["run_id"])
        value = json.loads(
            (
                root / "diagnostics" / (record["activity_attempt_id"] + ".json")
            ).read_text()
        )
        self.assertEqual(value["primary"]["operation"], "create container")
        self.assertEqual(
            value["final_category"], "opencode_container_cleanup_unverified"
        )
        self.assertIsNone(value["cleanup_verified"])
        self.assertFalse(self.runner.lock.locked())
        self.assertEqual(self.runner.active_backends, {})
