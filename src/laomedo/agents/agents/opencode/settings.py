"""Feature settings and fixed protocol values; mutable state has one owner."""

from __future__ import annotations

MIN_TOKEN_REMAINING_MS = 210000  # 180-second request timeout plus startup margin.


CLI_VERSION = "1.18.33"
CONFIG_SCHEMA_URL = "https://opencode.ai/config.json"
BROKER_HOST = "host.docker.internal"

# Independently owned worker sandbox pin. Initially the same reviewed image used
# by Codex; updating the Codex controller must not silently update this worker.
WORKER_IMAGE = "laomedo-codex-acp:0.159.2-2.1.1"
WORKER_IMAGE_ID = (
    "sha256:d3f53de292540a8e412aa34a43a975b467df2d21aa6bba290cee11956edc03aa"
)


# Covers the maximum validated Agent turn plus startup/teardown margin.
CONTROLLER_LIFETIME_SECONDS = 86400 + 120
CONTROLLER_LOG_TAIL_BYTES = 65536
