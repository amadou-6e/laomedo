"""Codex-native parent/telemetry interpretation and pinned pricing composition."""

from laomedo.agents.activity.timeline import project_normalized
from laomedo.agents.activity.utils import normalize_telemetry
from laomedo.agents.agents.codex.activity.cost import estimate


def _parent(thread):
    """Read explicitly reported Codex parent aliases; absent or malformed identity remains unknown."""
    parent = thread.get("parentThreadId")
    if not parent:
        source = thread.get("source")
        sub = source.get("subAgent", {}) if isinstance(source, dict) else {}
        spawn = sub.get("thread_spawn", {}) if isinstance(sub, dict) else {}
        parent = spawn.get("parent_thread_id") if isinstance(spawn, dict) else None
    return parent if isinstance(parent, str) and parent else None


def project(events, *, root_thread=None, model=None):
    """Project Codex observations through normalized shared lane assembly."""
    return project_normalized(
        events,
        root_thread=root_thread,
        model=model,
        parent_of=_parent,
        normalize_telemetry=normalize_telemetry,
        estimate=estimate,
        is_diagnostic=lambda method: False,
    )
