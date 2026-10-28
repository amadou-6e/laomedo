"""Feature settings and fixed protocol values; mutable state has one owner."""

from __future__ import annotations

LOSS_SECONDS = 5.0


SERVICE_STALE_SECONDS = 3.0


GRANT_TTL_SECONDS = 50.0


MAX_FROM_HEARTBEAT_SECONDS = 58.0


POLL_SECONDS = 0.25


LEASE_SECONDS = 60


POST_LOSS_WATCH_SECONDS = 5


LABEL_RUN = "laomedo.run_id"


LABEL_TOKEN = "laomedo.launch_token"
