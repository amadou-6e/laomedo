"""One-job native LFX process; graph code never shares broker credential custody."""

import asyncio
from contextlib import redirect_stdout
import json
import sys

from laomedo.github.node_runs.authority import GitHubRunAuthority
from laomedo.integrations.langflow.graph_admission.catalog import GitHubGraphCatalog
from laomedo.integrations.langflow.graph_admission.node_runs import (
    GitHubNodeRunAdmission,
)
from laomedo.integrations.langflow.execution.worker.channel import GraphWorkerChannel
from laomedo.integrations.langflow.execution.worker.errors import GraphWorkerError
from laomedo.integrations.langflow.execution.worker.models import (
    GraphWorkerJob,
    GraphWorkerResult,
)


class NativeGraphWorker:
    """Validate one approved graph before native component constructors execute."""

    job_model = GraphWorkerJob
    channel_type = GraphWorkerChannel

    def _event_manager(self, job):
        """Optional job-owned progress sink; the shared graph driver stays authoritative."""
        return None

    def _graph_class(self):
        """Use the installed parser; specializations may observe its existing scheduler."""
        from lfx.graph import Graph

        return Graph

    @staticmethod
    def _check_graph(catalog, job, payload):
        """Normalize the actual native payload and check its approved digest/source."""
        effective = GitHubNodeRunAdmission.executable_graph(
            catalog.effective_graph(payload)
        )
        if GitHubRunAuthority.digest_graph(effective) != job.graph_digest:
            raise GraphWorkerError()
        return effective

    async def _execute(self, job):
        """Run from the pinned snapshot after native parsing and before construction.

        Native migration/substitution can alter source before constructors. Parse
        with construction disabled, validate the actual resulting graph, then
        instantiate using the pinned native warm-graph construction interface.
        No upstream profile identity, broker cookie or credential is installed.
        """
        catalog = GitHubGraphCatalog(job.catalog)
        effective = self._check_graph(catalog, job, job.graph)
        graph = self._graph_class().from_payload(
            effective,
            flow_id=str(job.flow_id),
            user_id=str(job.job_id),
            instantiate_components=False,
            emit_extension_events=False,
        )
        self._check_graph(catalog, job, graph.raw_graph_data)
        nodes = {node["id"]: node["data"] for node in effective["nodes"]}
        if len(nodes) != len(effective["nodes"]) or set(graph.vertex_map) != set(nodes):
            raise GraphWorkerError()
        if any(
            graph.get_vertex(node_id).data != data for node_id, data in nodes.items()
        ):
            raise GraphWorkerError()
        # Native parameter projection can interpret posted field metadata or
        # edges after the raw source check. The constructor executes params, so
        # fence its actual input before any vertex is allowed to instantiate.
        if any(
            graph.get_vertex(node_id).params.get("code")
            != data["node"]["template"]["code"]["value"]
            or "code" in graph.get_vertex(node_id).load_from_db_fields
            for node_id, data in nodes.items()
        ):
            raise GraphWorkerError()
        terminals = graph.get_terminal_nodes()
        if job.outputs is not None and not set(job.outputs) <= set(terminals):
            raise GraphWorkerError()
        graph.set_run_id(job.job_id)
        graph.persist_messages = False
        graph._instantiate_components_in_vertices()
        graph._instantiate_components_on_initialize = True
        results = await graph.arun(
            inputs=job.inputs,
            outputs=job.outputs if job.outputs is not None else terminals,
            session_id=str(job.job_id),
            fallback_to_env_vars=False,
            event_manager=self._event_manager(job),
        )
        return [result.model_dump(mode="json") for result in results]

    async def run(self, incoming=None, outgoing=None):
        """Read one private bootstrap, run once, and emit only a bounded outcome.

        Standard graph prints go to stderr, outside the control channel. The
        host must discard/private-scope stderr and independently enforce timeout
        and container cleanup; the worker's timeout is not that security boundary.
        """
        incoming = sys.stdin.buffer if incoming is None else incoming
        outgoing = sys.stdout.buffer if outgoing is None else outgoing
        try:
            job = self.job_model.model_validate_json(
                json.dumps(GraphWorkerChannel.read_message(incoming), allow_nan=False)
            )
            self.channel_type.install(job, incoming, outgoing)
        except Exception:
            return 1
        try:
            with redirect_stdout(sys.stderr):
                outputs = await asyncio.wait_for(
                    self._execute(job), timeout=job.timeout_seconds
                )
            result = GraphWorkerResult(
                event="completed", job_id=job.job_id, outputs=outputs
            )
        except asyncio.TimeoutError:
            result = GraphWorkerResult(
                event="timed_out", job_id=job.job_id, code=GraphWorkerError.code
            )
        except Exception:
            result = GraphWorkerResult(
                event="failed", job_id=job.job_id, code=GraphWorkerError.code
            )
        try:
            GraphWorkerChannel.write_message(outgoing, result.model_dump(mode="json"))
        except GraphWorkerError:
            return 1
        return 0 if result.event == "completed" else 1
