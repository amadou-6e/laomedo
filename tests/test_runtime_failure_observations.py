"""Internal controls for safe failure facts, not live runner acceptance."""

import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from pydantic import ValidationError
from py_docker.errors import CleanupUnconfirmedError, DockerOperationError

from laomedo.agents.agents.base.models import AttemptFailureRecord, FailureObservation
from laomedo.agents.agents.base.utils import failure_observation, write_attempt_failure
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
        for code in (
            "opencode_transport_cleanup_failed",
            "executor_termination_unverified",
            "workspace_copy_mismatch",
            "outstanding_command_completion_unknown",
        ):
            with self.subTest(code=code):
                self.assertEqual(failure_observation(code=code).code, code)
        self.assertIsNone(failure_observation(code="codex_arbitrary_native_error").code)

    def test_private_writer_failure_cannot_raise(self):
        value = AttemptFailureRecord(
            primary=failure_observation(code="runner_transport_failed"),
            final_category="runner_transport_failed",
        )
        with (
            tempfile.TemporaryDirectory() as directory,
            patch(
                "laomedo.agents.agents.base.utils._json",
                side_effect=PermissionError("PRIVATE_PATH"),
            ),
        ):
            self.assertFalse(write_attempt_failure(Path(directory), "attempt", value))

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
