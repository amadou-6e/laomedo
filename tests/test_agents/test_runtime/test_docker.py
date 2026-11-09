"""Shared Docker ownership controls; no live daemon or provider acceptance."""

from importlib.util import find_spec
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch

from laomedo.agents.agents.base.docker import AgentDockerMechanism


@unittest.skipUnless(find_spec("py_docker"), "Requires optional runner dependencies")
class DockerMechanismTests(unittest.TestCase):
    """Protect pinned connections, ownership and fail-closed native outcomes."""

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
