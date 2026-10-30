"""Reserve host-owned capture context and dispatch with retained evidence."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from laomedo.agents.interface.models import AgentRequest
from laomedo.agents.activity.settings import REFUSALS
from laomedo.agents.activity.settings import Settings


def dispatch_with_capture(component, prepared):
    from laomedo.agents.activity.capture import ActivityCapture

    if component.operation not in {"fresh", "start", "resume"}:
        return component._http(*prepared)
    request = AgentRequest.from_component_request(prepared)
    capture = ActivityCapture(component)
    component._activity_capture = capture
    result = None
    refused = False
    try:
        if component.operation == "resume" and capture.capture:
            request = request.with_activity_attempt(capture.capture.invocation_id)
            # This polls only acceptance of our unique ID. It cannot consume
            # native receipts until the runner durably accepts this attempt.
            capture.bind(component._reference_run_id, capture.capture.invocation_id)
        result = component._http(*request.component_arguments())
        return result
    except Exception as exc:
        reference = getattr(exc, "run_reference", None)
        category = (
            reference.get("error_category") if isinstance(reference, dict) else None
        )
        refused = isinstance(category, str) and category in REFUSALS
        raise
    finally:
        capture.dispatched(result=result, refused=refused)


def now():
    return datetime.now(timezone.utc).isoformat()


def capture_for(component):
    """Opt-in host configuration; refuse dispatch if configured capture cannot reserve."""
    from laomedo.agents.activity.store import ActivityStore

    path = Settings().database
    if not path:
        return None
    graph = component.graph
    store = ActivityStore(path)
    execution = str(graph.run_id or "")
    if not execution:
        raise ValueError("agent_activity_execution_required")
    label = getattr(component._vertex, "display_name", None)
    from laomedo.agents.activity.models import (
        CaptureIdentity,
        ActivityInvocation,
    )

    identity = CaptureIdentity.from_values(
        str(component._user_id or ""),
        str(getattr(graph, "source_flow_id", None) or graph.flow_id or ""),
        component._vertex.id,
        execution=execution,
        node_label=label if isinstance(label, str) and label.strip() else None,
        provider=getattr(component, "activity_provider", "codex-cli"),
    )
    run = store.start(identity)
    return ActivityInvocation(store=store, invocation_id=run)
