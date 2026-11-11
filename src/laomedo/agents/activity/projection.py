"""Assemble shared display snapshots; new Activity never selects a provider parser."""

from laomedo.agents.activity.models import ActivityProjection


def project(events, *, root_thread=None, model=None, provider=None):
    """Read the newest normalized snapshot; retain historical database readability."""
    snapshots = [
        row["raw"]
        for row in events
        if row.get("raw", {}).get("method") == "activity/projection"
    ]
    if snapshots:
        value = max(snapshots, key=lambda row: row["revision"])["projection"]
        return ActivityProjection.model_validate(value).to_payload()
    if any(row.get("raw", {}).get("method") == "activity/record" for row in events):
        raise ValueError("activity_projection_not_available")
    # This branch is exclusively for already retained native rows from before
    # normalized ingestion, not a second contract for implementing providers.
    from laomedo.agents.activity.legacy import project_retained

    return project_retained(
        events, provider=provider, root_thread=root_thread, model=model
    )
