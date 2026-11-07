"""Real SDK watch semantics through the host boundary; no Docker/model dispatch."""

from importlib.util import find_spec
import unittest
from unittest.mock import Mock, patch

from laomedo.host.leases.models import ContainerIdentity
from laomedo.host.leases.utils import cleanup_after_loss, inspect_exact


@unittest.skipUnless(find_spec("py_docker"), "Requires declared Docker runtime")
class LeaseCleanupTests(unittest.TestCase):
    def setUp(self):
        from py_docker.containers.models import ContainerIdentity as RuntimeIdentity

        self.identity = ContainerIdentity(
            name="reserved",
            run_id="run",
            token="private",
            docker_endpoint="unix:///original.sock",
        )
        self.observed = RuntimeIdentity(
            id="a" * 64, name="reserved", labels={"laomedo.run_id": "run"}
        )

    def cleanup(self, observations, clock, duration):
        from py_docker.containers.watch import ContainerWatch

        containers = Mock()
        containers.reconcile.side_effect = observations
        with (
            patch("py_docker.Client") as client,
            patch("py_docker.containers.watch.time.monotonic", side_effect=clock),
            patch("py_docker.containers.watch.time.sleep"),
        ):
            client.return_value.__enter__.return_value.containers.watch.side_effect = (
                lambda reservation: ContainerWatch(containers, reservation)
            )
            result = cleanup_after_loss(self.identity, watch_seconds=duration)
            client.assert_called_once_with(
                environment={"DOCKER_HOST": "unix:///original.sock"}
            )
        return result, containers

    def test_delayed_creation_is_removed_by_immutable_identity(self):
        result, containers = self.cleanup(
            [None, self.observed, None], [0, 0, 0, 0.02], 0.01
        )
        self.assertEqual(result, (True, "removed_after_loss"))
        containers.remove.assert_called_once_with(self.observed, force=True)

    def test_creation_at_deadline_retains_late_owned_category(self):
        result, containers = self.cleanup([None, self.observed], [0, 0.02], 0.01)
        self.assertEqual(result, (False, "late_owned"))
        containers.remove.assert_not_called()

    def test_unobserved_create_is_not_confirmed_cleanup(self):
        result, containers = self.cleanup([None, None], [0, 0.02], 0.01)
        self.assertEqual(result, (False, "never_observed"))
        containers.remove.assert_not_called()

    def test_already_absent_normal_cleanup_is_confirmed(self):
        result, containers = self.cleanup([None, None], [0, 0], 0)
        self.assertEqual(result, (True, "absent"))
        containers.remove.assert_not_called()

    def test_unconfirmed_final_inspection_never_reports_removed(self):
        from py_docker.errors import DockerOperationError, OwnershipConflictError

        for final in (
            self.observed,
            DockerOperationError("unavailable"),
            OwnershipConflictError("foreign"),
        ):
            for duration, expected in ((0, "unknown"), (0.01, "late_unknown")):
                with self.subTest(final=type(final).__name__, duration=duration):
                    result, containers = self.cleanup(
                        [self.observed, final], [0, 0.02], duration
                    )
                    self.assertEqual(result, (False, expected))
                    containers.remove.assert_called_once_with(self.observed, force=True)

    def test_uncertain_or_foreign_resource_is_never_removed(self):
        from py_docker.errors import DockerOperationError, OwnershipConflictError

        for error, expected in (
            (DockerOperationError("unavailable"), "unknown"),
            (OwnershipConflictError("foreign"), "conflict"),
        ):
            with self.subTest(category=expected):
                result, containers = self.cleanup([error], [0], 0.01)
                self.assertEqual(result, (False, expected))
                containers.remove.assert_not_called()

    def test_foreign_inspection_does_not_invent_an_owned_id(self):
        from py_docker.containers.watch import ContainerWatch
        from py_docker.errors import OwnershipConflictError

        containers = Mock()
        containers.reconcile.side_effect = OwnershipConflictError("foreign")
        with patch("py_docker.Client") as client:
            client.return_value.__enter__.return_value.containers.watch.side_effect = (
                lambda reservation: ContainerWatch(containers, reservation)
            )
            self.assertEqual(inspect_exact(self.identity), ("conflict", None))
        containers.remove.assert_not_called()
