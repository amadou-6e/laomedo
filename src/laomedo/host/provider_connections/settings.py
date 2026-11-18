"""Fixed bounded login policy, independent of inference and runner readiness."""

ATTEMPT_SECONDS = 180
MAX_CONNECTIONS = 32
NATIVE_AUTH_CLEANUP_SECONDS = 20

# Fixed read-policy bounds; these never authorize a provider operation.
SUBSCRIPTION_FRESH_SECONDS = 60
SUBSCRIPTION_RETAIN_SECONDS = 600
SUBSCRIPTION_RETRY_SECONDS = 10
SUBSCRIPTION_CACHE_ENTRIES = 256
SUBSCRIPTION_WAIT_SECONDS = 180
