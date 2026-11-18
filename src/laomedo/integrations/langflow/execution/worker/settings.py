"""Fixed private-pipe protocol values and single-job worker deployment settings."""

from laomedo.integrations.langflow.execution.settings import BaseDockerRuntimeSettings

GRAPH_WORKER_PREFIX = b"LAOMEDO_GRAPH_V1 "
GRAPH_WORKER_MESSAGE_BYTES = 16 * 1024 * 1024
# Module the worker image runs; the supervisor and image entry point must agree.
GRAPH_WORKER_MODULE = "laomedo.integrations.langflow.execution.worker"


class GraphWorkerSettings(BaseDockerRuntimeSettings):
    """Explicit single-job worker deployment, never supplied by a graph or worker.

    `image_id` is the worker image digest. The inherited limits (1024 MiB memory,
    2 CPUs, 128 processes, 256 MiB /tmp) apply to each job's fresh container.
    """
