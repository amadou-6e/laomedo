"""Feature settings and fixed protocol values; mutable state has one owner."""

from __future__ import annotations

MIN_TOKEN_REMAINING_MS = 210000  # 180-second request timeout plus startup margin.


CLI_VERSION = "1.18.33"
CONFIG_SCHEMA_URL = "https://opencode.ai/config.json"
BROKER_HOST = "host.docker.internal"

# Registered controller and independently tagged worker recipes. IDs are local
# observations, never copied from another machine's build.
IMAGE = "laomedo-opencode:1.18.33"
WORKER_IMAGE = "laomedo-opencode-worker:codex-0.159.2-2.1.1"
WORKER_IMAGE_ID = None


# Covers the maximum validated Agent turn plus startup/teardown margin.
CONTROLLER_LIFETIME_SECONDS = 86400 + 120
CONTROLLER_LOG_TAIL_BYTES = 65536


MODEL_CATALOG_TTL_SECONDS = 30
