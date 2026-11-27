"""Provider job driver reusing pinned native catalog and constructor admission."""

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

    def _event_manager(self, job):
        from lfx.events.event_manager import create_default_event_manager

        channel = self.channel_type._active
        if channel is None or channel.job.job_id != job.job_id:
            from laomedo.integrations.langflow.execution.worker.errors import (
                GraphWorkerError,
            )

            raise GraphWorkerError()
        return create_default_event_manager(ProviderWorkerEvents(channel))
