"""Fixed saved-account run bounds; not model-turn or verification budgets."""

# Lifetime of a prepared, unconfirmed approval plan in seconds.
GITHUB_NODE_APPROVAL_SECONDS = 300
# Unconfirmed approval plans retained per broker; equal to the existing
# connection-attempt bound this authority previously shared.
GITHUB_NODE_PENDING_LIMIT = 32
