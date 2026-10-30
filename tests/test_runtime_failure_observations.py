"""Internal controls for safe failure facts, not live runner acceptance."""

import ast
import json
from importlib.util import find_spec
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from pydantic import ValidationError

if find_spec("py_docker"):
    from py_docker.errors import CleanupUnconfirmedError, DockerOperationError

from laomedo.agents.agents.base.models import AttemptFailureRecord, FailureObservation
from laomedo.agents.agents.base.agent import BaseAgent
from laomedo.agents.agents.base.utils import failure_observation
from laomedo.agents.errors import RunnerError
from laomedo.host.leases.client import LeaseClient
from laomedo.host.leases.models import LeaseCleanupObservation, LeaseLossObservation
from laomedo.host.leases.settings import LOSS_SECONDS, SERVICE_STALE_SECONDS
from laomedo.host.leases.utils import log_heartbeat_failure


class UnsafeFailure:
    """Trap accidental duck typing of an untrusted external object."""

    @property
    def code(self):
        raise AssertionError("untrusted property read")

    @property
    def operation(self):
        raise AssertionError("untrusted property read")


class RuntimeFailureObservationTests(unittest.TestCase):
    """Exercise redaction and compatibility without creating Docker clients."""

    @unittest.skipUnless(find_spec("py_docker"), "Requires the optional runner SDK")
    def test_sdk_primary_is_preserved_without_receipt_or_message(self):
        error = CleanupUnconfirmedError(
            "confirm owned container cleanup",
            receipt=UnsafeFailure(),
            primary=DockerOperationError("create container"),
        )
        value = failure_observation(error, stage="cleanup")
        self.assertEqual(value.sdk_code, "docker_cleanup_unconfirmed")
        self.assertEqual(value.primary_operation, "create container")
        self.assertNotIn("receipt", value.model_dump())
        self.assertEqual(failure_observation(UnsafeFailure()).code, None)

    @unittest.skipUnless(find_spec("py_docker"), "Requires the optional runner SDK")
    def test_syntax_valid_unknown_operation_is_omitted(self):
        value = failure_observation(DockerOperationError("secret_token_123"))
        self.assertIsNone(value.operation)
        self.assertNotIn("secret_token_123", value.model_dump_json())

    def test_optional_exception_fact_preserves_public_args(self):
        value = FailureObservation.from_values(
            stage="startup", code="runner_transport_failed"
        )
        error = RunnerError("runner_transport_failed", observation=value)
        self.assertEqual(error.args, ("runner_transport_failed",))
        self.assertEqual(str(error), "runner_transport_failed")
        self.assertIs(failure_observation(error), value)

    def test_cleanup_fact_requires_its_domain(self):
        primary = failure_observation(code="container_termination_unverified")
        with self.assertRaises(ValidationError):
            AttemptFailureRecord(
                primary=primary, final_category=None, cleanup_verified=True
            )
        value = AttemptFailureRecord(
            primary=primary,
            final_category="container_termination_unverified",
            cleanup_source="lease_result",
            cleanup_verified=True,
        )
        self.assertTrue(value.cleanup_verified)
        self.assertEqual(value.final_category, "container_termination_unverified")

    def test_fixed_path_codes_are_not_dropped(self):
        owners = {
            "opencode_transport_cleanup_failed": "agents/agents/opencode/agent.py",
            "executor_termination_unverified": "agents/agents/codex/split/executor.py",
            "workspace_copy_mismatch": "agents/workspaces/utils.py",
            "outstanding_command_completion_unknown": "agents/agents/codex/agent.py",
        }
        for code, owner in owners.items():
            with self.subTest(code=code):
                self.assertEqual(failure_observation(code=code).code, code)
                source = Path(__file__).resolve().parents[1] / "src/laomedo" / owner
                values = {
                    node.value
                    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8")))
                    if isinstance(node, ast.Constant) and isinstance(node.value, str)
                }
                self.assertIn(code, values)
        self.assertIsNone(failure_observation(code="codex_arbitrary_native_error").code)

    def test_private_writer_failure_cannot_raise(self):
        value = AttemptFailureRecord(
            primary=failure_observation(code="runner_transport_failed"),
            final_category="runner_transport_failed",
        )
        with (
            tempfile.TemporaryDirectory() as directory,
            patch(
                "laomedo.agents.agents.base.agent._json",
                side_effect=PermissionError("PRIVATE_PATH"),
            ),
        ):
            self.assertIsNone(
                BaseAgent._retain_attempt_failure(
                    Mock(),
                    Path(directory),
                    {"status": "failed", "error_category": "runner_transport_failed"},
                    {"id": "attempt"},
                    value.primary,
                    None,
                )
            )

    def test_os_log_never_contains_message_or_filename(self):
        error = PermissionError(13, "SECRET_MESSAGE", "SECRET_PATH")
        with self.assertLogs(level="WARNING") as logs:
            log_heartbeat_failure("service_wall", error)
        output = "\n".join(logs.output)
        self.assertIn("PermissionError", output)
        self.assertIn("errno=13", output)
        self.assertNotIn("SECRET", output)


class LeaseLossObservationTests(unittest.TestCase):
    """Verify loss signaling precedes every optional diagnostic effect."""

    def make_client(self, directory):
        client = LeaseClient.__new__(LeaseClient)
        client.state = client.dir = Path(directory)
        client.instance = "instance"
        client.lost = threading.Event()
        client.loss = client.result = None
        return client

    def test_events_precede_model_construction_and_first_loss_is_not_relabelled(self):
        with tempfile.TemporaryDirectory() as directory:
            client = self.make_client(directory)
            cancelled = threading.Event()

            def reject_model(**values):
                self.assertTrue(client.lost.is_set())
                self.assertTrue(cancelled.is_set())
                raise ValueError("diagnostic validation failed")

            with (
                patch(
                    "laomedo.host.leases.client._leases_utils._read_float",
                    return_value=None,
                ),
                patch(
                    "laomedo.host.leases.client._leases_utils._read_json",
                    return_value=None,
                ),
                patch(
                    "laomedo.host.leases.client.LeaseLossObservation",
                    side_effect=reject_model,
                ) as construct,
            ):
                client._check_service(cancelled)
                client._check_service(cancelled)
                self.assertEqual(construct.call_count, 1)
            self.assertIsNone(client.loss)

    def test_age_validation_and_security_limits(self):
        self.assertEqual((LOSS_SECONDS, SERVICE_STALE_SECONDS), (5.0, 3.0))
        with self.assertRaises(ValidationError):
            LeaseLossObservation(reason="service_instance_changed", age_seconds=4.0)
        self.assertEqual(
            LeaseLossObservation(
                reason="monotonic_heartbeat_stale", age_seconds=4.0
            ).age_seconds,
            4.0,
        )

    def test_each_existing_health_predicate_retains_only_its_first_reason(self):
        cases = [
            (None, 100.0, {"instance": "instance"}, "wall_heartbeat_unavailable", None),
            (
                100.0,
                None,
                {"instance": "instance"},
                "monotonic_heartbeat_unavailable",
                None,
            ),
            (
                100.0,
                102.0,
                {"instance": "instance"},
                "monotonic_heartbeat_future",
                -2.0,
            ),
            (100.0, 96.0, {"instance": "instance"}, "monotonic_heartbeat_stale", 4.0),
            (96.0, 100.0, {"instance": "instance"}, "wall_heartbeat_stale", 4.0),
            (100.0, 100.0, None, "service_record_unavailable", None),
            (100.0, 100.0, {"instance": "other"}, "service_instance_changed", None),
        ]
        for wall, monotonic, record, reason, age in cases:
            with (
                self.subTest(reason=reason),
                tempfile.TemporaryDirectory() as directory,
            ):
                client = self.make_client(directory)
                cancelled = threading.Event()
                with (
                    patch(
                        "laomedo.host.leases.client._leases_utils._read_float",
                        side_effect=[wall, monotonic],
                    ),
                    patch(
                        "laomedo.host.leases.client._leases_utils._read_json",
                        return_value=record,
                    ),
                    patch(
                        "laomedo.host.leases.client.time.monotonic", return_value=100.0
                    ),
                    patch("laomedo.host.leases.client.time.time", return_value=100.0),
                ):
                    client._check_service(cancelled)
                self.assertTrue(client.lost.is_set())
                self.assertTrue(cancelled.is_set())
                self.assertEqual(client.loss.reason, reason)
                self.assertEqual(client.loss.age_seconds, age)
                self.assertEqual(
                    json.loads((Path(directory) / "loss.json").read_text()),
                    client.loss.to_record(),
                )

    def test_finish_keeps_verified_result_before_loss_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            client = self.make_client(directory)
            client.stop_heartbeats = Mock()
            client.lost.set()
            result = {"reason": "done", "state": "absent", "cleanup_verified": True}
            with patch(
                "laomedo.host.leases.client._leases_utils._read_json",
                return_value=result,
            ):
                with self.assertRaisesRegex(RuntimeError, "lease_service_unverified"):
                    client.finish()
            self.assertIs(client.result, result)
            self.assertTrue(
                LeaseCleanupObservation.from_result(
                    result["cleanup_verified"], result["state"]
                ).verified
            )

    def test_finish_timeout_keeps_unavailable_result(self):
        with tempfile.TemporaryDirectory() as directory:
            client = self.make_client(directory)
            client.stop_heartbeats = Mock()
            with self.assertRaisesRegex(RuntimeError, "lease_service_unverified"):
                client.finish(timeout=0)
            self.assertIsNone(client.result)
