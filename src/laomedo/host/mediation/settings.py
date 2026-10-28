"""Feature settings and fixed protocol values; mutable state has one owner."""

from __future__ import annotations

READS = frozenset(
    {
        "git_fetch",
        "pr_list",
        "issue_list",
        "actions_read",
        "api_rest_read",
        "pr_read",
        "issue_read",
        "issue_query",
        "label_list",
    }
)


WRITES = frozenset(
    {
        "git_push",
        "pr_create",
        "pr_update",
        "issue_create",
        "api_rest_write",
        "api_graphql_mutation",
        "issue_update",
        "pr_node_update",
    }
)


OPERATIONS = READS | WRITES
