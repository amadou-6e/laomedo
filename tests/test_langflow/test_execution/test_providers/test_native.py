"""Real sandbox/pipe checks; native model replies are explicitly synthetic."""

import asyncio
from contextlib import ExitStack
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from laomedo.agents.connections.controllers import ProviderControllers
from laomedo.agents.connections.models import ConnectionRecord
from laomedo.agents.connections.service import ProviderConnections
from laomedo.integrations.langflow.execution.providers.admission import (
    ProviderGraphAdmission,
)
from laomedo.integrations.langflow.execution.providers.catalog import (
    ProviderComponentCatalog,
)
from laomedo.integrations.langflow.execution.providers.container import (
    DockerProviderGraphWorker,
)
from laomedo.integrations.langflow.execution.providers.dispatcher import (
    ProviderGraphDispatcher,
)
from laomedo.integrations.langflow.execution.worker.settings import GraphWorkerSettings
from laomedo.skills.registry.store import SkillStore
from support.docker import DockerTestContainer
from test_agents.test_connections.test_controllers import FakeNativeAgent


class SyntheticCompletedNative(FakeNativeAgent):
    """A completed native response for transport integration; no inference or edits."""

    def start_async(self, body, **kwargs):
        record = super().start_async(body, **kwargs)
        record.update(
            status="completed",
            provider="codex",
            answer="synthetic model reply through actual private pipe",
            attempt_finished=True,
            offered_skill=body.get("skill_ref"),
        )
        (self.state / "runs" / record["run_id"] / "record.json").write_text(
            json.dumps(record)
        )
        return record

    def cancel(self, run_id):
        return self.status(run_id)


class SyntheticWorkerTrace:
    """Bound failure diagnostics from this credential-free fixture worker only."""

    def __init__(self):
        self.create = asyncio.create_subprocess_exec
        self.readers = []
        self.content = bytearray()

    async def start(self, *arguments, **keywords):
        if (
            arguments[:2] == ("docker", "create")
            and arguments[-1] == "laomedo.integrations.langflow.execution.providers"
        ):
            # The same native driver and sandbox, with exception printing only
            # for this synthetic fixture. No credential-bearing run uses it.
            program = """
import asyncio, sys, traceback
from laomedo.integrations.langflow.execution.providers.native import NativeProviderGraphWorker
class DiagnosticWorker(NativeProviderGraphWorker):
    async def _execute(self, job):
        try:
            return await super()._execute(job)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            raise
sys.exit(asyncio.run(DiagnosticWorker().run()))
"""
            arguments = (*arguments[:-2], "-c", program)
        captured = arguments[:2] == ("docker", "start")
        if captured:
            keywords["stderr"] = asyncio.subprocess.PIPE
        process = await self.create(*arguments, **keywords)
        if captured:
            self.readers.append(asyncio.create_task(self.drain(process.stderr)))
        return process

    async def drain(self, stream):
        while chunk := await stream.read(8192):
            self.content.extend(chunk[: max(0, 131072 - len(self.content))])

    async def diagnostics(self):
        await asyncio.gather(*self.readers)
        return self.content.decode("utf-8", errors="replace")


@unittest.skipUnless(
    os.environ.get("LAOMEDO_TEST_GRAPH_WORKER_IMAGE"),
    "An explicitly built local worker image is required",
)
class ProviderNativeContainerTests(unittest.IsolatedAsyncioTestCase):
    """Execute actual Skill/Codex components with an inert host model boundary."""

    async def test_native_agent_component_uses_scoped_host_pipe_and_cleans_up(self):
        root = Path(__file__).resolve().parents[4]
        catalog = ProviderComponentCatalog(root / "components")
        with ExitStack() as resources:
            directory = resources.enter_context(
                tempfile.TemporaryDirectory(prefix="laomedo-provider-container-")
            )
            state = Path(directory)
            source = state / "skill-source"
            source.mkdir()
            (source / "SKILL.md").write_text(
                "---\nname: transport-skill\n---\nPRIVATE_HOST_SKILL_BYTES\n",
                encoding="utf-8",
            )
            reference = SkillStore(state / "skills").import_skill(
                "transport-skill", source
            )
            connections = ProviderConnections(state / "connections")
            resources.callback(connections.close)
            controllers = ProviderControllers(
                connections,
                state / "runs",
                state / "skills",
                state / "source",
                factory=SyntheticCompletedNative,
            )
            resources.callback(controllers.close)
            owner, flow, job_id = uuid4(), uuid4(), uuid4()
            account = ConnectionRecord(
                provider="codex",
                connection_id=uuid4(),
                credential_id=uuid4(),
                client_id="fixture",
                subject_hash="fixture",
                generation=1,
                label="Fixture",
            )
            connections._save(owner, [account])
            component = deepcopy(catalog._registry["laomedo"]["LaomedoCodexAgent"])
            skill = deepcopy(catalog._registry["laomedo"]["LaomedoSkill"])
            for name, value in {
                "skill_id": reference["skill_id"],
                "revision_id": reference["revision_id"],
            }.items():
                skill["template"][name]["value"] = value
            for name, value in {
                "task": "Synthetic transport check",
                "model": "fixture",
                "effort": "low",
                "provider_connection": str(account.connection_id),
                "operation": "fresh",
            }.items():
                component["template"][name]["value"] = value
            graph = {
                "nodes": [
                    {
                        "id": "codex-fixture",
                        "type": "genericNode",
                        "data": {
                            "id": "codex-fixture",
                            "type": "LaomedoCodexAgent",
                            "node": component,
                        },
                    },
                    {
                        "id": "skill-fixture",
                        "type": "genericNode",
                        "data": {
                            "id": "skill-fixture",
                            "type": "LaomedoSkill",
                            "node": skill,
                        },
                    },
                ],
                "edges": [
                    {
                        "source": "skill-fixture",
                        "target": "codex-fixture",
                        "data": {
                            "sourceHandle": {
                                "id": "skill-fixture",
                                "name": "skill",
                                "dataType": "LaomedoSkill",
                                "output_types": ["Data"],
                            },
                            "targetHandle": {
                                "id": "codex-fixture",
                                "fieldName": "skill_reference",
                                "inputTypes": ["Data"],
                                "type": "other",
                            },
                        },
                    }
                ],
            }
            prepared = ProviderGraphAdmission(
                connections, catalog.admission, skill_store=controllers.skill_store
            ).prepare(owner, "lease", flow, job_id, graph, timeout_seconds=60.0)
            capability = controllers.graph_runs.admit(prepared.plan)
            dispatcher = ProviderGraphDispatcher(
                controllers, capability, prepared.plan.graph_digest
            )
            worker = DockerProviderGraphWorker(
                GraphWorkerSettings(
                    image_id=os.environ["LAOMEDO_TEST_GRAPH_WORKER_IMAGE"],
                    lease_state=state / "leases",
                ),
                prepared.job,
                dispatcher,
            )
            environment = worker._environment()
            environment["PYTHONPATH"] = str(root / "src")
            lease = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "laomedo.host.leases.service_cli",
                    "serve",
                    "--state",
                    str(state / "leases"),
                ],
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            try:
                deadline = time.monotonic() + 15
                while not (state / "leases" / "service.json").exists():
                    self.assertIsNone(lease.poll(), "Lease supervisor failed to start")
                    self.assertLess(time.monotonic(), deadline)
                    await asyncio.sleep(0.05)
                trace = SyntheticWorkerTrace()
                events = []
                worker.on_event = events.append
                with patch("asyncio.create_subprocess_exec", new=trace.start):
                    try:
                        result = await asyncio.wait_for(worker.run(prepared.job), 65)
                    except Exception:
                        self.fail(await trace.diagnostics())
                diagnostics = await trace.diagnostics()
                self.assertEqual(result.event, "completed", diagnostics)
                self.assertIn(
                    "synthetic model reply through actual private pipe",
                    result.model_dump_json(),
                )
                self.assertEqual(
                    dispatcher.node_outcomes["codex-fixture"]["state"], "succeeded"
                )
                native = next(iter(controllers.slots.values())).runner
                records = list((native.state / "runs").glob("*/record.json"))
                self.assertEqual(len(records), 1)
                self.assertEqual(
                    json.loads(records[0].read_text())["offered_skill"],
                    {
                        key: reference[key]
                        for key in ("skill_id", "revision_id", "tree_hash")
                    },
                )
                self.assertNotIn(
                    "PRIVATE_HOST_SKILL_BYTES", prepared.job.model_dump_json()
                )
                self.assertEqual(worker._jobs, {})
                self.assertTrue(all(stop.settled for stop in worker.stops))
                self.assertFalse(any(stop.cancel_confirmed for stop in worker.stops))
                self.assertIsNone(controllers.graph_runs.finish(capability))
                self.assertEqual(
                    {event.event for event in events}, {"build_start", "end_vertex"}
                )

                # Exercise accountless text composition in the same real native
                # sandbox. Only the first transport fixture used an inert Agent.
                from laomedo.integrations.langflow.assistant.catalog import (
                    ComponentCatalog,
                )
                from laomedo.integrations.langflow.assistant.models import DraftGraph

                graph, _ = ComponentCatalog(catalog._registry).compile(
                    DraftGraph.model_validate(
                        {
                            "nodes": [
                                {
                                    "key": "join",
                                    "component_type": "input_output/CombineText",
                                    "fields": {
                                        "text1": "Clean",
                                        "text2": "text workflow",
                                        "delimiter": " ",
                                    },
                                },
                                {
                                    "key": "out",
                                    "component_type": "input_output/TextOutput",
                                },
                            ],
                            "edges": [
                                {
                                    "source": "join",
                                    "output": "combined_text",
                                    "target": "out",
                                    "input": "input_value",
                                }
                            ],
                        }
                    )
                )
                text = ProviderGraphAdmission(connections, catalog.admission).prepare(
                    owner, "lease", flow, uuid4(), graph, timeout_seconds=60.0
                )
                self.assertEqual(text.plan.nodes, ())
                text_capability = controllers.graph_runs.admit(text.plan)
                text_dispatcher = ProviderGraphDispatcher(
                    controllers, text_capability, text.plan.graph_digest
                )
                text_worker = DockerProviderGraphWorker(
                    worker.settings, text.job, text_dispatcher
                )
                trace = SyntheticWorkerTrace()
                with patch("asyncio.create_subprocess_exec", new=trace.start):
                    text_result = await asyncio.wait_for(text_worker.run(text.job), 65)
                self.assertEqual(
                    text_result.event, "completed", await trace.diagnostics()
                )
                self.assertIn("Clean text workflow", text_result.model_dump_json())
                self.assertEqual(text_worker.stops, ())
            finally:
                if lease.poll() is None:
                    lease.terminate()
                await asyncio.to_thread(lease.wait, timeout=10)


@unittest.skipUnless(
    os.environ.get("LAOMEDO_TEST_GRAPH_WORKER_IMAGE"),
    "An explicitly built local worker image is required",
)
class ArbitraryWorkerPythonTests(unittest.TestCase):
    """The OS boundary holds even when arbitrary Python bypasses graph admission."""

    def test_python_has_no_host_environment_socket_network_or_writable_root(self):
        image = os.environ["LAOMEDO_TEST_GRAPH_WORKER_IMAGE"]
        self.assertRegex(image, r"^sha256:[0-9a-f]{64}$")
        program = """
import errno, json, os, pathlib, socket
result = {'uid': os.getuid(), 'docker_socket': pathlib.Path('/var/run/docker.sock').exists(), 'dotenv': pathlib.Path('/opt/laomedo/.env').exists()}
result['private_environment'] = any(key.startswith(('GH_', 'GITHUB_', 'LAOMEDO_PIN', 'OPENAI_', 'ANTHROPIC_', 'CODEX_')) for key in os.environ)
try:
    pathlib.Path('/opt/laomedo/root-write-test').write_text('should be refused')
    result['root_denied'] = False
except OSError as error:
    result['root_denied'] = error.errno in (errno.EACCES, errno.EROFS)
try:
    with socket.create_connection(('172.17.0.1', 17885), timeout=1):
        result['network_denied'] = False
except OSError:
    result['network_denied'] = True
print(json.dumps(result))
"""
        with DockerTestContainer() as container:
            result = subprocess.run(
                [
                    *container.arguments(),
                    "--network=none",
                    "--read-only",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "--user",
                    "65532:65532",
                    "--pids-limit",
                    "128",
                    "--memory",
                    "1g",
                    "--cpus",
                    "2",
                    "--tmpfs",
                    "/tmp:rw,nosuid,nodev,size=64m",
                    "--entrypoint",
                    "python",
                    image,
                    "-c",
                    program,
                ],
                capture_output=True,
                timeout=25,
            )
        self.assertEqual(result.returncode, 0, "sandbox check failed")
        self.assertEqual(
            json.loads(result.stdout),
            {
                "uid": 65532,
                "docker_socket": False,
                "dotenv": False,
                "private_environment": False,
                "root_denied": True,
                "network_denied": True,
            },
        )
