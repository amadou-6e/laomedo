"""Explicit refusal of ambiguous offline source migration."""


class ManualMigrationRequired(ValueError):
    """Selected source cannot be migrated without a human decision."""
