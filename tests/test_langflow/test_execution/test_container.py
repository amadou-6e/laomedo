"""Deployment boundaries checked before a private job enters Docker."""

import copy
import asyncio
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import time
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from pydantic import ValidationError

from laomedo.integrations.langflow.execution.container import DockerGraphWorker
from laomedo.integrations.langflow.execution.errors import GraphWorkerError
from laomedo.integrations.langflow.execution.settings import GraphWorkerSettings
from laomedo.github.connections.models import GitHubNodeReadResult, GitHubNodeSelection
from laomedo.github.connections.run_authority import GitHubRunAuthority
from laomedo.github.connections.worker_access import GitHubWorkerAccess
from laomedo.integrations.langflow.execution.models import (
    GraphWorkerCall,
    GraphWorkerJob,
)
from test_github.test_connections.test_run_authority import NodeConnectionFixture


class DockerDeploymentTests(unittest.TestCase):
    """Refuse ambient credentials and weakened runtime confinement."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="laomedo-worker-settings-")
        self.addCleanup(self.directory.cleanup)
        self.settings = GraphWorkerSettings(
            image_id="sha256:" + "a" * 64,
            lease_state=Path(self.directory.name),
        )
        self.worker = DockerGraphWorker(self.settings, None, None)

    def sandbox(self):
        """A daemon inspection with the required independent isolation controls."""
        return {
            "Config": {"Image": self.settings.image_id, "User": "65532:65532"},
            "HostConfig": {
                "NetworkMode": "none",
                "ReadonlyRootfs": True,
                "CapDrop": ["ALL"],
                "SecurityOpt": ["no-new-privileges"],
                "Memory": 1024 * 1024 * 1024,
                "PidsLimit": 128,
                "NanoCpus": 2_000_000_000,
                "Tmpfs": {"/tmp": "rw,nosuid,nodev,size=256m"},
            },
        }

    def test_weakened_daemon_configuration_refuses_before_dispatch(self):
        valid = self.sandbox()
        self.worker._verify_sandbox(valid)
        for section, key, value in (
            ("Config", "Image", "mutable:tag"),
            ("Config", "User", "root"),
            ("HostConfig", "NetworkMode", "bridge"),
            ("HostConfig", "ReadonlyRootfs", False),
            ("HostConfig", "CapDrop", []),
            ("HostConfig", "SecurityOpt", []),
            ("HostConfig", "Binds", ["/:/host"]),
            ("HostConfig", "Privileged", True),
            ("HostConfig", "NanoCpus", 0),
            ("HostConfig", "PortBindings", {"80/tcp": [{}]}),
            ("HostConfig", "Tmpfs", {}),
        ):
            with self.subTest(control=key):
                changed = copy.deepcopy(valid)
                changed[section][key] = value
                with self.assertRaises(GraphWorkerError):
                    self.worker._verify_sandbox(changed)
        with self.assertRaises(GraphWorkerError):
            self.worker._verify_sandbox(None)

    def test_docker_environment_does_not_inherit_provider_or_remote_authority(self):
        with patch.dict(
            os.environ,
            {
                "GH_TOKEN": "private",
                "OPENAI_API_KEY": "private",
                "DOCKER_HOST": "tcp://remote:2375",
                "DOCKER_CONTEXT": "remote",
            },
        ):
            environment = self.worker._environment()
        self.assertNotIn("GH_TOKEN", environment)
        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertNotIn("DOCKER_HOST", environment)
        self.assertEqual(environment["DOCKER_CONTEXT"], "desktop-linux")

    def test_environment_cannot_override_host_admitted_configuration(self):
        with patch.dict(os.environ, {"IMAGE_ID": "mutable:tag", "CPUS": "999"}):
            settings = GraphWorkerSettings(
                image_id=self.settings.image_id, lease_state=self.settings.lease_state
            )
        self.assertEqual(settings.cpus, 2.0)
        with self.assertRaises(ValidationError):
            GraphWorkerSettings(
                image_id="mutable:tag", lease_state=self.settings.lease_state
            )

    def test_repository_state_is_not_a_private_lease_store(self):
        (Path(self.directory.name) / ".git").mkdir()
        with self.assertRaises(ValidationError):
            GraphWorkerSettings(
                image_id=self.settings.image_id,
                lease_state=Path(self.directory.name) / "runtime",
            )


class SyntheticContainerReader:
    """Synthetic provider boundary; the supervisor and native worker remain real."""

    def __init__(self, connections):
        self.connections = connections
        self.calls = []

    async def read(self, scope, connection_id, **values):
        self.calls.append(values)
        authorization = await self.connections.authorize_read(scope, connection_id, 12)
        return GitHubNodeReadResult(
            authorization=authorization,
            payload={
                "issue": {
                    "repository": "synthetic/private",
                    "number": 1,
                    "url": "https://github.com/synthetic/private/issues/1",
                    "title": "Synthetic supervisor read",
                    "body": "Private pipe result",
                    "state": "open",
                    "labels": [],
                },
                "operation": {"status": "not_requested"},
            },
        )


class WorkerCancellationTests(unittest.IsolatedAsyncioTestCase):
    """Revocation interrupts an in-flight provider read rather than waiting for it."""

    async def test_revocation_cancels_pending_read_without_releasing_output(self):
        started, stopped = asyncio.Event(), asyncio.Event()

        async def blocked_read(*arguments):
            started.set()
            try:
                await asyncio.Future()
            finally:
                stopped.set()

        job_id = uuid4()
        authority = SimpleNamespace(
            workers={job_id: SimpleNamespace(expires_at=time.monotonic() + 60)},
            clock=time.monotonic,
        )
        worker = DockerGraphWorker(
            None, authority, SimpleNamespace(inspect=blocked_read)
        )
        call = GraphWorkerCall(
            request_id=1,
            capability="w" * 43,
            request={
                "job_id": job_id,
                "vertex_id": "issue-1",
                "labels": [],
                "state": "open",
            },
        )
        pending = asyncio.create_task(worker._read(call, threading.Event()))
        await asyncio.wait_for(started.wait(), 1.0)
        authority.workers.clear()
        with self.assertRaises(GraphWorkerError):
            await asyncio.wait_for(pending, 1.0)
        self.assertTrue(stopped.is_set())


@unittest.skipUnless(
    os.environ.get("LAOMEDO_TEST_GRAPH_WORKER_IMAGE"),
    "An explicitly built local graph worker image is required",
)
class ContainerSupervisorTests(unittest.IsolatedAsyncioTestCase):
    """Real Docker lifecycle and lease process, with synthetic GitHub responses.

    The test does not terminate the broker's process tree or claim crash recovery.
    Deployment must start the lease service independently of the broker tree.
    """

    async def test_admitted_read_revokes_authority_and_removes_its_container(self):
        from test_langflow.test_execution.test_worker import NativeGraphWorkerTests

        native = NativeGraphWorkerTests()
        self.addCleanup(native.doCleanups)
        native.github_graph("issue")
        template = native.graph["nodes"][0]["data"]["node"]["template"]
        template["repository_url"]["value"] = "https://github.com/synthetic/private"
        connections = NodeConnectionFixture()
        authority = GitHubRunAuthority(connections)
        job_id, flow_id = uuid4(), uuid4()
        selection = GitHubNodeSelection(
            vertex_id=native.node["id"],
            kind="issue",
            connection_id=connections.connection,
            repository=connections.repository,
            number=1,
        )
        reference, _ = await authority.prepare(
            connections.scope(), flow_id, native.graph, [selection]
        )
        await authority.admit(
            reference,
            connections.scope(),
            flow_id=flow_id,
            graph=native.graph,
            job_id=job_id,
            approved=False,
        )
        capability = authority.issue_worker(job_id, deadline=authority.clock() + 60.0)
        reader = SyntheticContainerReader(connections)
        with tempfile.TemporaryDirectory(prefix="laomedo-worker-lease-") as directory:
            environment = dict(os.environ, DOCKER_CONTEXT="desktop-linux")
            service = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "laomedo.host.leases.service_cli",
                    "serve",
                    "--state",
                    directory,
                ],
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                deadline = time.monotonic() + 15.0
                while not (Path(directory) / "service.alive").exists():
                    self.assertIsNone(service.poll(), "Lease service failed to start")
                    self.assertLess(time.monotonic(), deadline)
                    await asyncio.sleep(0.05)
                settings = GraphWorkerSettings(
                    image_id=os.environ["LAOMEDO_TEST_GRAPH_WORKER_IMAGE"],
                    lease_state=Path(directory),
                )
                worker = DockerGraphWorker(
                    settings, authority, GitHubWorkerAccess(authority, reader)
                )
                result = await worker.run(
                    GraphWorkerJob(
                        job_id=job_id,
                        flow_id=flow_id,
                        graph=native.graph,
                        graph_digest=authority.digest_graph(native.graph),
                        catalog=native.catalog,
                        capability=capability,
                        timeout_seconds=30.0,
                    )
                )
                self.assertEqual(result.event, "completed")
                self.assertIn("Private pipe result", result.model_dump_json())
                self.assertEqual(len(reader.calls), 1)
                self.assertNotIn(job_id, authority.workers)
                self.assertNotIn(job_id, authority.jobs)
                self.assertEqual(worker._jobs, {})
            finally:
                service.terminate()
                await asyncio.to_thread(service.wait, timeout=10)
