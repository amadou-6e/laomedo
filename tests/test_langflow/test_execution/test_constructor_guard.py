"""Native component construction must use the approved source after parsing."""

from importlib.util import find_spec
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

if find_spec("lfx") is None:
    raise unittest.SkipTest("Optional native executor is not installed")

from lfx.components.input_output.text_output import TextOutputComponent
from lfx.graph import Graph

from laomedo.github.connections.run_authority import GitHubRunAuthority
from laomedo.integrations.langflow.authentication.catalog import GitHubGraphCatalog
from laomedo.integrations.langflow.authentication.node_runs import (
    GitHubNodeRunAdmission,
)
from laomedo.integrations.langflow.execution.errors import GraphWorkerError
from laomedo.integrations.langflow.execution.models import GraphWorkerJob
from laomedo.integrations.langflow.execution.worker import NativeGraphWorker


class ConstructorGuardTests(unittest.IsolatedAsyncioTestCase):
    """Refuse a changed native constructor parameter before executing it."""

    async def test_changed_parameter_cannot_run_code_after_raw_graph_validation(self):
        node = TextOutputComponent(input_value="approved").to_frontend_node()
        catalog = GitHubGraphCatalog.capture(
            {"io": {node["data"]["type"]: node["data"]["node"]}}
        )
        graph = GitHubNodeRunAdmission.executable_graph({"nodes": [node], "edges": []})
        job = GraphWorkerJob(
            job_id=uuid4(),
            flow_id=uuid4(),
            graph=graph,
            graph_digest=GitHubRunAuthority.digest_graph(graph),
            catalog=catalog.snapshot,
            capability="w" * 43,
            timeout_seconds=30.0,
        )
        original = Graph.from_payload
        with tempfile.TemporaryDirectory(
            prefix="laomedo-constructor-test-"
        ) as directory:
            marker = Path(directory) / "executed"

            def altered_projection(*args, **kwargs):
                native_graph = original(*args, **kwargs)
                native_graph.get_vertex(node["id"]).params["code"] = (
                    "from lfx.custom.custom_component.component import Component\n"
                    f"open({str(marker)!r}, 'w').write('unexpected')\n"
                    "class Injected(Component):\n    pass\n"
                )
                return native_graph

            with (
                patch.object(Graph, "from_payload", side_effect=altered_projection),
                patch("lfx.utils.flow_validation.validate_flow_for_current_settings"),
            ):
                with self.assertRaises(GraphWorkerError):
                    await NativeGraphWorker()._execute(job)
            self.assertFalse(marker.exists())
