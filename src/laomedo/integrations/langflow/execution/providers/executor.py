"""Isolated native execution backend for the API-only account broker's assistant."""

import asyncio
from uuid import UUID, uuid4

from laomedo.agents.connections.errors import ProviderConnectionError
from laomedo.github.contract import repository_from_url
from laomedo.github.issues.gateway import GitHubIssueGateway
from laomedo.github.transport.rest.public import PublicGitHubIssueTransport
from laomedo.host.mediation.store import MediationStore
from laomedo.integrations.langflow.execution.providers.admission import (
    ProviderGraphAdmission,
)
from laomedo.integrations.langflow.execution.providers.container import (
    DockerProviderGraphWorker,
)
from laomedo.integrations.langflow.execution.providers.dispatcher import (
    ProviderGraphDispatcher,
)
from laomedo.integrations.langflow.execution.worker.errors import GraphWorkerError


class ProviderGraphExecutor:
    """Start only approved snapshots; retain unresolved cleanup without replaying work."""

    def __init__(self, settings, catalog, controllers):
        self.settings = settings
        self.catalog = catalog
        self.controllers = controllers
        self.admission = ProviderGraphAdmission(controllers.service, catalog.admission)
        self.workers = {}
        self.uncertain = {}

    def browser(self, owner):
        """Require the real verified browser context, not graph or MCP selectors."""
        from langflow.services.auth.context import (
            AUTH_METHOD_JWT,
            get_current_auth_context,
        )
        from laomedo.integrations.langflow.provider_connections.bindings import (
            ProviderGraphBindings,
        )

        authentication = get_current_auth_context()
        browser = ProviderGraphBindings.session.get()
        if (
            ProviderGraphBindings.service is not self.controllers.service
            or authentication is None
            or authentication.method != AUTH_METHOD_JWT
            or browser is None
            or browser.profile_id != owner
        ):
            raise ProviderConnectionError("provider_session_required")
        self.controllers.service.check_lease(browser.lease_hash)
        return browser

    def _public_gateway(self, prepared):
        """Use anonymous REST only; saved GitHub accounts are outside this example."""
        transports = {
            repository_from_url(issue.repository_url): PublicGitHubIssueTransport(
                repository_from_url(issue.repository_url)
            )
            for issue in prepared.issues
        }
        return GitHubIssueGateway(
            transports,
            MediationStore(self.controllers.root / "graph-public-issues.sqlite"),
            lambda reference: None,
        )

    def validate_graph(self, owner, flow_id, graph):
        """Dry-plan current isolated support without creating jobs or native authority."""
        browser = self.browser(owner)
        return self.admission.prepare(
            owner, browser.lease_hash, flow_id or uuid4(), uuid4(), graph
        )

    async def execute(self, snapshot, request, actor, run_id, *, on_event=None):
        """Project the actual isolated result into the existing assistant evidence owner."""
        from lfx.graph.schema import RunOutputs
        from langflow.api.v1.schemas import RunResponse
        from langflow.services.deps import get_job_service
        from langflow.services.database.models.jobs.model import JobStatus

        owner, job_id = UUID(str(actor.id)), UUID(str(run_id))
        browser = self.browser(owner)
        if (
            UUID(str(snapshot.user_id)) != owner
            or job_id in self.workers
            or job_id in self.uncertain
        ):
            raise ProviderConnectionError("verified_review_unavailable")
        graph = snapshot.data
        if request.input_value:
            graph = self.admission.input_graph(
                graph, request.input_value, request.input_type
            )
        prepared = self.admission.prepare(
            owner, browser.lease_hash, UUID(str(snapshot.id)), job_id, graph
        )
        job = prepared.job.model_copy(
            update={
                "outputs": (
                    [request.output_component] if request.output_component else None
                )
            }
        )
        jobs = get_job_service()
        self.workers[job_id] = None
        worker = dispatcher = capability = None
        created = succeeded = False
        try:
            # Native job UUID uniqueness is the durable replay barrier. This
            # API-only app has no native queue consumer or graph recovery loop.
            await jobs.create_job(
                job_id,
                UUID(str(snapshot.id)),
                user_id=owner,
                initial_metadata={"execution_owner": "laomedo-isolated-provider"},
            )
            created = True
            await jobs.update_job_status(job_id, JobStatus.IN_PROGRESS)
            capability = self.controllers.graph_runs.admit(prepared.plan)
            gateway = await asyncio.to_thread(self._public_gateway, prepared)
            dispatcher = ProviderGraphDispatcher(
                self.controllers,
                capability,
                prepared.plan.graph_digest,
                prepared.issues,
                gateway=gateway,
            )
            worker = DockerProviderGraphWorker(self.settings, job, dispatcher)
            worker.on_event = on_event
            self.workers[job_id] = worker
            result = await worker.run(job)
            self.browser(owner)
            if result.event != "completed":
                raise GraphWorkerError()
            succeeded = True
            return RunResponse(
                outputs=[RunOutputs.model_validate(value) for value in result.outputs],
                session_id=str(job_id),
            )
        finally:
            self.workers.pop(job_id, None)
            if worker is None and capability is not None:
                await asyncio.shield(
                    asyncio.to_thread(self.controllers.finish_graph, capability)
                )
            elif worker is not None and (
                worker.stops is None or any(not item.settled for item in worker.stops)
            ):
                self.uncertain[job_id] = worker
            if created:
                nodes = (
                    list(dispatcher.node_outcomes.values())
                    if dispatcher is not None
                    else []
                )
                await asyncio.shield(
                    jobs.update_job_metadata(
                        job_id,
                        {
                            "isolated_provider_nodes": nodes,
                            "native_cleanup_confirmed": job_id not in self.uncertain,
                        },
                    )
                )
                await asyncio.shield(
                    jobs.update_job_status(
                        job_id,
                        JobStatus.COMPLETED if succeeded else JobStatus.FAILED,
                        finished_timestamp=True,
                    )
                )

    async def reconcile(self):
        """Retry cleanup of revoked receipts only; never restart a graph or native task."""
        for job_id, worker in tuple(self.uncertain.items()):
            try:
                await worker._finish_job(job_id)
            except Exception:
                continue
            if worker.stops is not None and all(item.settled for item in worker.stops):
                from langflow.services.deps import get_job_service

                try:
                    await get_job_service().update_job_metadata(
                        job_id, {"native_cleanup_confirmed": True}
                    )
                except Exception:
                    continue
                self.uncertain.pop(job_id, None)
