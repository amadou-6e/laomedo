"""Claude diagnostics and normalized timeline policy; no Codex price inference."""

from laomedo.agents.activity.timeline import project_normalized
from laomedo.agents.activity.utils import normalize_telemetry


def estimate(model, usage):
    """Retain unknown cost unless Claude-native pricing has actually been verified."""
    return {
        "currency": "USD",
        "catalog_date": None,
        "model": model,
        "basis": "Claude-native pricing is not independently verified; not a subscription invoice",
        "source": None,
        "source_record": None,
        "amount": None,
        "reason": "Claude-native pricing is unavailable.",
    }


def project(events, *, root_thread=None, model=None):
    """Interpret Claude result diagnostics without assuming Codex model rates."""
    return project_normalized(
        events,
        root_thread=root_thread,
        model=model,
        parent_of=lambda thread: thread.get("parentThreadId"),
        normalize_telemetry=normalize_telemetry,
        estimate=estimate,
        is_diagnostic=lambda method: method == "claude/result",
    )
