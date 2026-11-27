"""Provider job driver reusing pinned native catalog and constructor admission."""

from laomedo.integrations.langflow.execution.worker.native import NativeGraphWorker
from laomedo.integrations.langflow.execution.providers.channel import (
    ProviderWorkerChannel,
)
from laomedo.integrations.langflow.execution.providers.models import ProviderWorkerJob


class NativeProviderGraphWorker(NativeGraphWorker):
    """Install only a credential-free provider pipe in this fresh process."""

    job_model = ProviderWorkerJob
    channel_type = ProviderWorkerChannel
