"""Native cold-worker execution and pre-constructor source rejection."""

from importlib.util import find_spec
import importlib.util
from io import BytesIO
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from uuid import uuid4

from support.docker import DockerTestContainer

if find_spec("lfx") is None:
    raise unittest.SkipTest("Optional native executor is not installed")

from lfx.components.input_output.text_output import TextOutputComponent

from laomedo.github.node_runs.authority import GitHubRunAuthority
from laomedo.integrations.langflow.graph_admission.catalog import GitHubGraphCatalog
from laomedo.integrations.langflow.graph_admission.node_runs import (
    GitHubNodeRunAdmission,
)
from laomedo.integrations.langflow.execution.channel import GraphWorkerChannel
from laomedo.integrations.langflow.execution.models import (
    GraphWorkerCall,
    GraphWorkerJob,
    GraphWorkerResult,
)


class NativeGraphWorkerTests(unittest.TestCase):
    """Real native graph execution; no providers, GitHub or host credentials."""

    def setUp(self):
        component = TextOutputComponent(input_value="isolated native result")
        self.configure_graph(component)

    def configure_graph(self, component):
        """Capture the real component's source/metadata, without provider execution."""
        self.node = component.to_frontend_node()
        catalog = GitHubGraphCatalog.capture(
            {"io": {self.node["data"]["type"]: self.node["data"]["node"]}}
        )
        self.graph = GitHubNodeRunAdmission.executable_graph(
            {"nodes": [self.node], "edges": []}
        )
        self.catalog = catalog.snapshot

    def invoke(self, graph, directory, reply=None):
        job = GraphWorkerJob(
            job_id=uuid4(),
            flow_id=uuid4(),
            graph=graph,
            graph_digest=GitHubRunAuthority.digest_graph(graph),
            catalog=self.catalog,
            capability="w" * 43,
            timeout_seconds=30.0,
        )
        bootstrap = BytesIO()
        GraphWorkerChannel.write_message(bootstrap, job.private_payload())
        if reply is not None:
            GraphWorkerChannel.write_message(bootstrap, {"request_id": 1, **reply})
        source = Path(__file__).resolve().parents[3] / "src"
        allowed = {
            "PATH",
            "SYSTEMROOT",
            "WINDIR",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "APPDATA",
            "LOCALAPPDATA",
        }
        environment = {
            key: value for key, value in os.environ.items() if key.upper() in allowed
        }
        environment.update(
            {
                "PYTHONPATH": str(source),
                "HOME": str(directory),
                "LANGFLOW_CONFIG_DIR": str(Path(directory) / "config"),
                "LFX_CONFIG_DIR": str(Path(directory) / "config"),
                "LANGFLOW_DO_NOT_TRACK": "true",
            }
        )
        result = subprocess.run(
            self.worker_command(),
            input=bootstrap.getvalue(),
            cwd=directory,
            env=environment,
            capture_output=True,
            timeout=60,
        )
        # Stderr belongs to this private job and is not echoed into CI logs.
        incoming = BytesIO(result.stdout)
        if reply is not None:
            call = GraphWorkerCall.model_validate(
                GraphWorkerChannel.read_message(incoming)
            )
            self.assertEqual(call.request.job_id, job.job_id)
            self.assertEqual(call.request.vertex_id, self.node["id"])
            self.assertEqual(call.request.number, 1)
            self.assertEqual(call.capability, job.capability)
        outcome = GraphWorkerResult.model_validate(
            GraphWorkerChannel.read_message(incoming)
        )
        self.assertEqual(outcome.job_id, job.job_id)
        self.assertNotIn("w" * 43, outcome.model_dump_json())
        return result.returncode, outcome

    def worker_command(self):
        """Execute the installed native driver in a cold local Python process."""
        return [sys.executable, "-m", "laomedo.integrations.langflow.execution"]

    def github_graph(self, kind):
        """Load the maintained native node; keep broker replies explicitly synthetic."""
        root = Path(__file__).resolve().parents[3]
        spec = importlib.util.spec_from_file_location(
            "isolated_worker_" + kind,
            root / "components" / "laomedo" / ("github_" + kind + ".py"),
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        self.addCleanup(sys.modules.pop, spec.name, None)
        spec.loader.exec_module(module)
        component = (
            module.LaomedoGitHubPR if kind == "pr" else module.LaomedoGitHubIssue
        )()
        component.set(
            repository_url="https://github.com/owner/repo",
            labels=[],
            state="open",
            **{kind + "_choice": "#1 Selected target"},
        )
        self.configure_graph(component)

    def test_native_github_nodes_use_private_pipe_for_reads(self):
        for kind in ("pr", "issue"):
            with self.subTest(kind=kind):
                self.github_graph(kind)
                item = {
                    "repository": "owner/repo",
                    "number": 1,
                    "url": "https://github.com/owner/repo/"
                    + ("pull" if kind == "pr" else "issues")
                    + "/1",
                    "title": "Synthetic broker title",
                    "body": "Synthetic broker body",
                    "state": "open",
                    "labels": [],
                }
                payload = {kind: item, "operation": {"status": "not_requested"}}
                with tempfile.TemporaryDirectory(
                    prefix="laomedo-worker-test-"
                ) as directory:
                    status, outcome = self.invoke(
                        self.graph, directory, reply={"payload": payload}
                    )
                self.assertEqual(status, 0)
                self.assertIn("Synthetic broker body", outcome.model_dump_json())

    def test_broker_refusal_never_falls_back_to_host_github_credentials(self):
        self.github_graph("pr")
        with tempfile.TemporaryDirectory(prefix="laomedo-worker-test-") as directory:
            _, outcome = self.invoke(
                self.graph,
                directory,
                reply={"code": "github_node_authorization_unavailable"},
            )
        self.assertIn(
            "github_node_authorization_unavailable", outcome.model_dump_json()
        )
        self.assertNotIn("pr_service_not_configured", outcome.model_dump_json())

    def test_actual_native_terminal_output_runs_in_a_fresh_process(self):
        with tempfile.TemporaryDirectory(prefix="laomedo-worker-test-") as directory:
            status, outcome = self.invoke(self.graph, directory)
        self.assertEqual(status, 0)
        self.assertEqual(outcome.event, "completed")
        self.assertIn("isolated native result", outcome.model_dump_json())

    def test_edited_python_cannot_execute_during_native_construction(self):
        code = self.graph["nodes"][0]["data"]["node"]["template"]["code"]
        code["value"] += '\nopen("executed", "w").write("unexpected execution")\n'
        with tempfile.TemporaryDirectory(prefix="laomedo-worker-test-") as directory:
            status, outcome = self.invoke(self.graph, directory)
            self.assertFalse((Path(directory) / "executed").exists())
        self.assertNotEqual(status, 0)
        self.assertEqual(outcome.event, "failed")

    def test_forged_loader_metadata_cannot_replace_the_pinned_component_source(self):
        """Exercise native construction with a real alternate import target present.

        Protection comes from the pinned-source and native loader handling, not
        from the constructor fence. The constructor fence is covered by the
        patched-projection test in test_constructor_guard.py.
        """
        data = self.graph["nodes"][0]["data"]["node"]
        data.setdefault("metadata", {})["module"] = "forged_loader"
        data["metadata"]["class_name"] = "TextOutputComponent"
        data["template"]["_type"] = "PythonInterpreter"
        for output in data["outputs"]:
            output["types"] = ["Tool"]
        with tempfile.TemporaryDirectory(prefix="laomedo-worker-loader-") as directory:
            (Path(directory) / "forged_loader.py").write_text(
                'from pathlib import Path\nPath("untrusted_loader_executed").write_text("not allowed")\n',
                encoding="utf-8",
            )
            _, outcome = self.invoke(self.graph, directory)
            self.assertFalse((Path(directory) / "untrusted_loader_executed").exists())
        # The forged metadata must not select another class: the run completes
        # only with the pinned TextOutputComponent output.
        self.assertEqual(outcome.event, "completed")
        self.assertIn("isolated native result", outcome.model_dump_json())

    def test_code_input_cannot_be_retyped_to_execute_a_different_file_value(self):
        """Protection by the earlier source checks, not the constructor fence.

        A retyped FileInput is refused before any constructor runs. The new
        constructor fence is covered only by the patched-projection test in
        test_constructor_guard.py. GraphWorkerError uses one generic code, so
        this test pins the exact refusal code but not which check fired.
        """
        field = self.graph["nodes"][0]["data"]["node"]["template"]["code"]
        field["_input_type"] = "FileInput"
        field["file_path"] = (
            "from lfx.custom.custom_component.component import Component\n"
            "from pathlib import Path\n"
            "class OtherComponent(Component):\n"
            "    def __init__(self, **kwargs):\n"
            "        Path('untrusted_file_code_executed').write_text('not allowed')\n"
            "        super().__init__(**kwargs)\n"
        )
        with tempfile.TemporaryDirectory(
            prefix="laomedo-worker-code-input-"
        ) as directory:
            _, outcome = self.invoke(self.graph, directory)
            self.assertFalse(
                (Path(directory) / "untrusted_file_code_executed").exists()
            )
        self.assertEqual(outcome.event, "failed")
        self.assertEqual(outcome.code, "github_graph_runtime_unavailable")


@unittest.skipUnless(
    os.environ.get("LAOMEDO_TEST_GRAPH_WORKER_IMAGE"),
    "An explicitly built local graph worker image is required",
)
class ContainerGraphWorkerTests(NativeGraphWorkerTests):
    """Same native contract inside a real container; broker replies are synthetic."""

    def worker_command(self):
        """Use a pinned image with no host mounts, network or inherited credentials."""
        image = os.environ["LAOMEDO_TEST_GRAPH_WORKER_IMAGE"]
        self.assertRegex(image, r"^sha256:[0-9a-f]{64}$")
        return [
            *self.container.arguments(),
            "--interactive",
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
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=256m",
            image,
        ]

    def invoke(self, graph, directory, reply=None):
        """Guarantee owned-container cleanup even if a native child hangs."""
        with DockerTestContainer() as container:
            self.container = container
            return super().invoke(graph, directory, reply)
