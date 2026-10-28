"""Feature settings and fixed protocol values; mutable state has one owner."""

from __future__ import annotations

MIN_TOKEN_REMAINING_MS = 210000  # 180-second request timeout plus startup margin.


CLI_VERSION = "1.18.33"

# Independently owned worker sandbox pin. Initially the same reviewed image used
# by Codex; updating the Codex controller must not silently update this worker.
WORKER_IMAGE = "laomedo-codex-boundary:0.159.2"
WORKER_IMAGE_ID = "sha256:7b79ce12be47d6c8262dd4043895112d204416bda5cd891d124775df55587239"
