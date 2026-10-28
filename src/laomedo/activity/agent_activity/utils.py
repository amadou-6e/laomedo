"""Reserve host-owned capture context and dispatch with retained evidence."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from laomedo.agents.contracts.models import RunnerRequest
import laomedo.activity.agent_activity.constants as _agent_activity_constants
import os


def dispatch_with_capture(component, prepared):
    import laomedo.activity.agent_activity.capture as _agent_activity_capture

    if component.operation not in {"fresh", "start", "resume"}:
        return component._http(*prepared)
    request = RunnerRequest.from_component_request(prepared)
    capture = _agent_activity_capture.RunnerCapture(component)
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
        refused = (
            isinstance(category, str) and category in _agent_activity_constants.REFUSALS
        )
        raise
    finally:
        capture.dispatched(result=result, refused=refused)


def now():
    return datetime.now(timezone.utc).isoformat()


def capture_for(component):
    """Opt-in host configuration; refuse dispatch if configured capture cannot reserve."""
    import laomedo.activity.agent_activity.store as _agent_activity_store

    path = os.environ.get("LAOMEDO_AGENT_ACTIVITY_DB")
    if not path:
        return None
    graph = component.graph
    store = _agent_activity_store.ActivityStore(path)
    execution = str(graph.run_id or "")
    if not execution:
        raise ValueError("agent_activity_execution_required")
    label = getattr(component._vertex, "display_name", None)
    from laomedo.activity.agent_activity.models import (
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
