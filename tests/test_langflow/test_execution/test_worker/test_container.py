"""Deployment boundaries checked before a private job enters Docker."""

import copy
import json
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
from unittest.mock import patch, AsyncMock, Mock
from uuid import uuid4
from support.docker import DockerTestContainer

from pydantic import SecretStr, ValidationError
from laomedo.host.leases.models import ContainerIdentity

from laomedo.integrations.langflow.execution.worker.container import DockerGraphWorker
from laomedo.integrations.langflow.execution.base import BaseDockerRuntime
from laomedo.integrations.langflow.execution.worker.errors import GraphWorkerError
from laomedo.integrations.langflow.execution.worker.settings import GraphWorkerSettings
from laomedo.integrations.langflow.execution.settings import DOCKER_CONTROL_OUTPUT_BYTES
from laomedo.github.node_runs.models import (
    GitHubNodeReadResult,
    GitHubNodeSelection,
)
from laomedo.github.node_runs.authority import GitHubRunAuthority
from laomedo.github.node_runs.worker_access import GitHubWorkerAccess
from laomedo.integrations.langflow.execution.worker.models import (
    GraphWorkerCall,
    GraphWorkerJob,
    GraphWorkerScope,
)
from test_github.test_node_runs.test_authority import NodeConnectionFixture


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


class DockerEndpointTests(unittest.IsolatedAsyncioTestCase):
    """Registration and later Docker control stay on the exact inspected daemon."""

    async def test_local_context_is_pinned_into_environment_and_lease_registration(
        self,
    ):
        endpoint = "npipe:////./pipe/dockerDesktopLinuxEngine"
        worker = DockerGraphWorker(
            SimpleNamespace(
                docker_context="desktop-linux", lease_state=Path(tempfile.gettempdir())
            ),
            None,
            None,
        )
        worker._control = AsyncMock(
            return_value=subprocess.CompletedProcess(
                [], 0, json.dumps(endpoint).encode(), b""
            )
        )
        environment = {"DOCKER_CONTEXT": "desktop-linux"}
        self.assertEqual(await worker._local_context(environment), endpoint)
        self.assertNotIn("DOCKER_CONTEXT", environment)
        self.assertEqual(environment["DOCKER_HOST"], endpoint)
        identity = ContainerIdentity(
            name="fixture",
            run_id=str(uuid4()),
            token=SecretStr("a" * 32),
            docker_endpoint=endpoint,
        )
        with patch(
            "laomedo.integrations.langflow.execution.base.LeaseClient", autospec=True
        ) as factory:
            await worker._start_lease(identity, threading.Event())
        self.assertEqual(factory.call_args.kwargs["docker_endpoint"], endpoint)

    async def test_remote_or_malformed_daemon_does_not_change_control_environment(self):
        worker = DockerGraphWorker(
            SimpleNamespace(docker_context="desktop-linux"), None, None
        )
        for endpoint in ("tcp://remote:2375", {}, None, 1):
            with self.subTest(endpoint=endpoint):
                worker._control = AsyncMock(
                    return_value=subprocess.CompletedProcess(
                        [], 0, json.dumps(endpoint).encode(), b""
                    )
                )
                environment = {"DOCKER_CONTEXT": "desktop-linux"}
                with self.assertRaises(GraphWorkerError):
                    await worker._local_context(environment)
                self.assertEqual(environment, {"DOCKER_CONTEXT": "desktop-linux"})


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
        live = {job_id: time.monotonic() + 60}
        authority = SimpleNamespace(
            worker_remaining=lambda key: (
                None if key not in live else live[key] - time.monotonic()
            ),
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
        live.clear()
        with self.assertRaises(GraphWorkerError):
            await asyncio.wait_for(pending, 1.0)
        self.assertTrue(stopped.is_set())

    async def test_authority_cleanup_failure_still_removes_the_owned_container(self):
        job = SimpleNamespace(
            job_id=uuid4(), flow_id=uuid4(), graph_digest="fixture", graph={}
        )
        worker = DockerGraphWorker(None, None, None)
        worker._job_scope = Mock(
            return_value=GraphWorkerScope(
                owner_id=uuid4(),
                flow_id=job.flow_id,
                graph_digest=job.graph_digest,
                first_vertex="fixture",
            )
        )
        worker._validate_graph = Mock()
        worker._authorize_job = AsyncMock()
        worker._local_context = AsyncMock()
        worker._environment = Mock(return_value={})
        lease = SimpleNamespace(finish=Mock())

        async def register():
            return lease

        worker._start_lease = Mock(
            side_effect=lambda *args: asyncio.create_task(register())
        )
        worker._control = AsyncMock(return_value=SimpleNamespace(returncode=1))
        worker._finish_job = AsyncMock(
            side_effect=RuntimeError("fixture cleanup failure")
        )
        worker._remove = AsyncMock()
        with self.assertRaisesRegex(RuntimeError, "fixture cleanup failure"):
            await worker.run(job)
        worker._remove.assert_awaited_once()
        lease.finish.assert_called_once()
        self.assertNotIn(job.job_id, worker._jobs)


@unittest.skipUnless(
    os.environ.get("LAOMEDO_TEST_GRAPH_WORKER_IMAGE"),
    "An explicitly built local worker image is required",
)
class DockerControlOutputTests(unittest.IsolatedAsyncioTestCase):
    """Container output cannot turn trusted Docker control into an unbounded buffer."""

    async def test_oversized_container_output_is_refused_without_returning_its_body(
        self,
    ):
        image = os.environ["LAOMEDO_TEST_GRAPH_WORKER_IMAGE"]
        with tempfile.TemporaryDirectory(prefix="laomedo-control-limit-") as directory:
            runtime = BaseDockerRuntime(
                GraphWorkerSettings(image_id=image, lease_state=Path(directory))
            )
            for descriptor in (1, 2):
                with (
                    self.subTest(stream=descriptor),
                    DockerTestContainer() as container,
                ):
                    program = f"import os;os.write({descriptor}, b'x'*{DOCKER_CONTROL_OUTPUT_BYTES * 2})"
                    with self.assertRaises(GraphWorkerError):
                        await asyncio.wait_for(
                            runtime._control(
                                [
                                    *container.run_arguments(),
                                    "--network=none",
                                    "--cap-drop=ALL",
                                    "--security-opt=no-new-privileges",
                                    "--read-only",
                                    "--user",
                                    "65532:65532",
                                    "--pids-limit",
                                    "128",
                                    "--memory",
                                    "1g",
                                    "--cpus",
                                    "2",
                                    "--entrypoint",
                                    "python",
                                    image,
                                    "-c",
                                    program,
                                ],
                                runtime._environment(),
                            ),
                            timeout=20.0,
                        )


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
        from test_langflow.test_execution.test_worker.test_native import (
            NativeGraphWorkerTests,
        )

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
                while not (Path(directory) / "service.json").exists():
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
