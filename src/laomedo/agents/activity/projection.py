"""Read common display snapshots without importing provider implementations."""

from laomedo.agents.activity.models import ActivityProjection


def project(events):
    """Return the latest common snapshot, or an unknown empty invocation view."""
    snapshots = [
        row["raw"]
        for row in events
        if row.get("raw", {}).get("method") == "activity/projection"
    ]
    if snapshots:
        value = max(snapshots, key=lambda row: row["revision"])["projection"]
        return ActivityProjection.model_validate(value).to_payload()
    if not events:
        return ActivityProjection.empty().to_payload()
    raise ValueError("activity_projection_not_available")
