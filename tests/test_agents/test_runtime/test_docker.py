"""Shared Docker ownership controls; no live daemon or provider acceptance."""

from importlib.util import find_spec
from pathlib import Path
import threading
import unittest
from unittest.mock import MagicMock, Mock, patch

from laomedo.agents.agents.base.runtime import AgentDockerMechanism


@unittest.skipUnless(find_spec("py_docker"), "Requires optional runner dependencies")
class DockerMechanismTests(unittest.TestCase):
    """Protect pinned connections, ownership and fail-closed native outcomes."""

    def test_borrowed_job_client_is_not_replaced_or_closed(self):
        client = Mock()
        job = Mock()
        cancelled = threading.Event()
        with patch("py_docker.Client") as factory:
            result = AgentDockerMechanism.execute_job(
                client, job, cancelled=cancelled, deadline=100, cleanup_seconds=5
            )
        self.assertIs(result, client.jobs.run.return_value)
        client.jobs.run.assert_called_once_with(
            job, cancelled=cancelled, deadline=100, cleanup_seconds=5
        )
        client.close.assert_not_called()
        factory.assert_not_called()

    def test_borrowed_recovery_stops_at_first_uncertain_receipt(self):
        client = Mock()
        failure = RuntimeError("uncertain")
        client.sessions.recover.side_effect = failure
        with self.assertRaises(RuntimeError) as caught:
            AgentDockerMechanism.recover_receipts(
                client, [Path("first.json"), Path("second.json")]
            )
        self.assertIs(caught.exception, failure)
        client.sessions.recover.assert_called_once_with(Path("first.json"))
        client.close.assert_not_called()

    def test_session_preserves_admission_and_cleanup_budgets(self):
        client = Mock()
        native = MagicMock()
        client.sessions.open.return_value = native
        request = Mock()
        with AgentDockerMechanism.session(
            client, request, deadline=123, cleanup_seconds=7
        ):
            pass
        client.sessions.open.assert_called_once_with(
            request, deadline=123, cleanup_seconds=7
        )

    def test_explicit_session_close_preserves_native_cached_failure(self):
        session = Mock()
        failure = RuntimeError("cleanup uncertain")
        session.close.side_effect = failure
        for _ in range(2):
            with self.assertRaises(RuntimeError) as caught:
                AgentDockerMechanism.close_session(session)
            self.assertIs(caught.exception, failure)

    def test_session_passes_body_failure_to_native_cleanup_without_closing_client(self):
        client = Mock()
        native = MagicMock()
        native.__enter__.return_value = native
        native.__exit__.return_value = False
        client.sessions.open.return_value = native
        request = Mock()
        primary = RuntimeError("execution failed")
        with self.assertRaises(RuntimeError) as caught:
            with AgentDockerMechanism.session(client, request) as session:
                self.assertIs(session, native)
                raise primary
        self.assertIs(caught.exception, primary)
        client.sessions.open.assert_called_once_with(request)
        self.assertIs(native.__exit__.call_args.args[1], primary)
        client.close.assert_not_called()

    def test_session_cleanup_uncertainty_is_not_reported_as_success(self):
        client = Mock()
        native = MagicMock()
        client.sessions.open.return_value = native
        failure = RuntimeError("cleanup uncertain")
        native.__exit__.side_effect = failure
        with self.assertRaises(RuntimeError) as caught:
            with AgentDockerMechanism.session(client, Mock()):
                pass
        self.assertIs(caught.exception, failure)
        client.close.assert_not_called()

    def test_session_startup_failure_does_not_claim_an_opened_scope(self):
        client = Mock()
        failure = RuntimeError("startup failed")
        client.sessions.open.side_effect = failure
        with self.assertRaises(RuntimeError) as caught:
            with AgentDockerMechanism.session(client, Mock()):
                self.fail("startup unexpectedly succeeded")
        self.assertIs(caught.exception, failure)
        client.close.assert_not_called()

    def test_supplied_endpoint_is_detached_from_mutable_host_configuration(self):
        environment = {"DOCKER_HOST": "unix:///selected.sock"}
        mechanism = AgentDockerMechanism(environment)
        environment["DOCKER_HOST"] = "unix:///other.sock"
        with patch("py_docker.Client") as factory:
            with mechanism.client():
                pass
        factory.assert_called_once_with(
            environment={"DOCKER_HOST": "unix:///selected.sock"}
        )
        factory.return_value.__exit__.assert_called_once()

    def test_job_uncertainty_keeps_native_failure_and_closes_its_client(self):
        failure = RuntimeError("native cleanup uncertain")
        cancelled = threading.Event()
        job = Mock()
        with patch("py_docker.Client") as factory:
            factory.return_value.__enter__.return_value.jobs.run.side_effect = failure
            with self.assertRaises(RuntimeError) as caught:
                AgentDockerMechanism({"DOCKER_HOST": "unix:///selected.sock"}).run_job(
                    job, cancelled=cancelled, deadline=100, cleanup_seconds=10
                )
        self.assertIs(caught.exception, failure)
        factory.return_value.__enter__.return_value.jobs.run.assert_called_once_with(
            job, cancelled=cancelled, deadline=100, cleanup_seconds=10
        )
        factory.return_value.__exit__.assert_called_once()

    def test_recovery_stops_on_uncertainty_and_uses_the_selected_receipt_service(self):
        receipts = [Path("first.json"), Path("second.json")]
        with patch("py_docker.Client") as factory:
            client = factory.return_value.__enter__.return_value
            client.jobs.recover.side_effect = RuntimeError("uncertain")
            with self.assertRaisesRegex(RuntimeError, "uncertain"):
                AgentDockerMechanism({}).recover(receipts, kind="job")
        client.jobs.recover.assert_called_once_with(receipts[0])
        client.sessions.recover.assert_not_called()
        factory.return_value.__exit__.assert_called_once()

    def test_unknown_recovery_kind_never_connects(self):
        with patch("py_docker.Client") as factory:
            with self.assertRaises(ValueError):
                AgentDockerMechanism({}).recover([Path("first.json")], kind="unknown")
        factory.assert_not_called()
