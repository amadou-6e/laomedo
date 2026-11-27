"""Provider job driver reusing pinned native catalog and constructor admission."""

from lfx.graph import Graph

from laomedo.integrations.langflow.execution.worker.native import NativeGraphWorker
from laomedo.integrations.langflow.execution.providers.channel import (
    ProviderWorkerChannel,
    ProviderWorkerEvents,
)
from laomedo.integrations.langflow.execution.providers.models import ProviderWorkerJob


class NativeProviderGraphWorker(NativeGraphWorker):
    """Install only a credential-free provider pipe in this fresh process."""

    job_model = ProviderWorkerJob
    channel_type = ProviderWorkerChannel

    def _graph_class(self):
        return ProviderProgressGraph

    def _event_manager(self, job):
        from lfx.events.event_manager import create_default_event_manager

        channel = self.channel_type._active
        if channel is None or channel.job.job_id != job.job_id:
            from laomedo.integrations.langflow.execution.worker.errors import (
                GraphWorkerError,
            )

            raise GraphWorkerError()
        return create_default_event_manager(ProviderWorkerEvents(channel))


class ProviderProgressGraph(Graph):
    """Observe native vertex construction without reimplementing native scheduling.

    LFX's batch `arun` path passes the event manager to components but emits no
    vertex start/end events. Its sequential `async_start` path does. Observe the
    existing batch vertex operation so the worker retains its native scheduler.
    """

    async def build_vertex(self, vertex_id, *, event_manager=None, **kwargs):
        if event_manager is not None:
            event_manager.on_build_start(data={"id": vertex_id})
        result = await super().build_vertex(
            vertex_id, event_manager=event_manager, **kwargs
        )
        if event_manager is not None:
            event_manager.on_end_vertex(
                data={
                    "build_data": {
                        "id": vertex_id,
                        "valid": result.valid,
                        "data": result.result_dict.model_dump(mode="json"),
                    }
                }
            )
        return result
