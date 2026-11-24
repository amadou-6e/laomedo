"""Explicit real-Docker acceptance of shared mechanisms; never invokes a model."""

import os
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from laomedo.docker import DockerRuntime


@unittest.skipUnless(
    os.environ.get("LAOMEDO_TEST_DOCKER_IMAGE"),
    "Set LAOMEDO_TEST_DOCKER_IMAGE to an installed image with /bin/sh",
)
class DockerIntegrationTests(unittest.TestCase):
    """Check actual process I/O, exact removal and receipt reconciliation."""

    def test_job_finishes_and_removes_its_container(self):
        from py_docker.containers.models import ContainerSpec
        from py_docker.jobs.models import ContainerJob
        from docker.errors import NotFound
        from py_docker.streams.models import StreamLimits

        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / "job.json"
            mechanism = DockerRuntime(None)
            with mechanism.client() as client:
                name = "laomedo-docker-test-" + uuid4().hex
                job = ContainerJob(
                    spec=ContainerSpec(
                        image=client.images.resolve(
                            os.environ["LAOMEDO_TEST_DOCKER_IMAGE"]
                        ),
                        name=name,
                        entrypoint=["/bin/sh"],
                        command=["-c", "printf shared-job"],
                        user="10001:10001",
                        read_only=True,
                        network_mode="none",
                        cap_drop=["ALL"],
                    ),
                    limits=StreamLimits(seconds=15, max_bytes=4096),
                    receipt_path=receipt,
                    wait_timeout_seconds=5,
                )
                result = mechanism.execute_job(client, job)
                self.assertEqual((result.exit_code, result.stdout), (0, b"shared-job"))
                with self.assertRaises(NotFound):
                    client.sdk.containers.get(name)
                mechanism.recover_receipts(client, [receipt], kind="job")
                self.assertFalse(receipt.exists())

    def test_interactive_session_exec_and_repeated_close_confirm_exact_removal(self):
        from py_docker.containers.models import ContainerSpec
        from py_docker.sessions.models import ContainerSession
        from py_docker.streams.models import StreamLimits

        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / "session.json"
            mechanism = DockerRuntime(None)
            with mechanism.client() as client:
                request = ContainerSession(
                    spec=ContainerSpec(
                        image=client.images.resolve(
                            os.environ["LAOMEDO_TEST_DOCKER_IMAGE"]
                        ),
                        name="laomedo-docker-test-" + uuid4().hex,
                        entrypoint=["/bin/sh"],
                        command=["-c", 'read line; printf "%s\\n" "$line"'],
                        user="10001:10001",
                        read_only=True,
                        network_mode="none",
                        stdin_open=True,
                        cap_drop=["ALL"],
                    ),
                    limits=StreamLimits(seconds=15, max_bytes=4096),
                    receipt_path=receipt,
                )
                with mechanism.session(client, request) as session:
                    identity = session.identity
                    result = mechanism.run_command(
                        client,
                        identity,
                        ["/bin/sh", "-c", "printf shared-exec"],
                        StreamLimits(seconds=5, max_bytes=4096),
                    )
                    self.assertEqual(
                        (result.exit_code, result.stdout), (0, b"shared-exec")
                    )
                    session.write(b"shared-session\n")
                    self.assertEqual(session.read_line().data, b"shared-session\n")
                    self.assertEqual(session.wait(timeout=5), 0)
                mechanism.close_session(session)
                self.assertTrue(session.cleanup_confirmed)
                self.assertIsNone(client.containers.inspect(identity))
                mechanism.recover_receipts(client, [receipt])
                self.assertFalse(receipt.exists())
