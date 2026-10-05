"""Fail-closed Work Graph checks before a Langflow stage reserves a run."""

from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json

from laomedo.workflow_run_store import LaunchError

from .model import GraphSnapshot


def _digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False).encode("utf-8")
    return "sha256:" + sha256(encoded).hexdigest()


def _item(graph, key):
    return next((item for item in graph.items if item.key == key), None)


def relevant_content_digest(graph: GraphSnapshot, work_key: str) -> str:
    """Hash selected work and its transitive prerequisites, excluding fetch time."""
    if not isinstance(graph, GraphSnapshot) or not isinstance(work_key, str):
        raise LaunchError("invalid_work_graph")
    items = {item.key: item for item in graph.items}
    edges = {}
    for edge in graph.dependencies:
        edges.setdefault(edge.dependent, []).append(edge)
    seen, pending = set(), [work_key]
    while pending:
        key = pending.pop()
        if key in seen:
            continue
        seen.add(key)
        pending.extend(edge.prerequisite for edge in edges.get(key, ()))
    relevant_edges = [edge for edge in graph.dependencies if edge.dependent in seen]
    return _digest({"repository": graph.repository,
        "schema_version": graph.schema_version,
        "connector_version": graph.connector_version,
        "source_complete": graph.source_complete,
        "items": [asdict(items[key]) for key in sorted(seen) if key in items],
        "unresolved_keys": sorted(seen - items.keys()),
        "edges": [asdict(edge) for edge in relevant_edges]})


def preflight(frozen: GraphSnapshot, current: GraphSnapshot, work_key: str,
              *, choice=None, override=None) -> dict:
    if (not isinstance(frozen, GraphSnapshot) or
            not isinstance(current, GraphSnapshot) or
            frozen.repository != current.repository):
        raise LaunchError("invalid_work_graph")
    if not current.source_complete:
        raise LaunchError("source_incomplete")
    selected = _item(current, work_key)
    if selected is None or selected.state != "OPEN":
        raise LaunchError("selected_item_unavailable")
    original = _item(frozen, work_key)
    if original is None:
        raise LaunchError("frozen_item_unavailable")
    frozen_content = relevant_content_digest(frozen, work_key)
    current_content = relevant_content_digest(current, work_key)
    changed = frozen_content != current_content
    if changed and choice not in {"pinned", "refreshed"}:
        raise LaunchError("stale_unacknowledged")
    if choice not in {None, "pinned", "refreshed"}:
        raise LaunchError("invalid_source_choice")
    readiness = current.readiness().get(work_key)
    if readiness in {"unknown", "cyclic"}:
        raise LaunchError("prerequisite_" + readiness)
    if readiness == "blocked":
        open_edges = {(edge.prerequisite, edge.dependent)
            for edge in current.dependencies if edge.dependent == work_key
            and (blocker := _item(current, edge.prerequisite)) is not None
            and blocker.state == "OPEN"}
        if (not isinstance(override, dict) or
                set(override) != {"prerequisite", "dependent", "rationale"} or
                not isinstance(override["rationale"], str) or
                not override["rationale"].strip() or
                open_edges != {(override["prerequisite"], override["dependent"])}):
            raise LaunchError("open_prerequisite")
    elif readiness != "ready" or override is not None:
        raise LaunchError("override_not_applicable")
    bound = current if choice == "refreshed" else frozen
    if not bound.source_complete:
        raise LaunchError("bound_source_incomplete")
    bound_item = _item(bound, work_key)
    if bound_item is None or bound_item.state != "OPEN":
        raise LaunchError("bound_item_unavailable")
    work = {"key": bound_item.key, "repository": bound_item.repository,
            "number": bound_item.number, "url": bound_item.url,
            "updated_at": bound_item.updated_at,
            "body_digest": _digest(bound_item.body)}
    return {"work_snapshot": work, "work_snapshot_id": _digest(work),
            "input_digest": _digest({"work": work, "body": bound_item.body,
                                     "graph_snapshot_id": bound.snapshot_id}),
            "selected_graph_snapshot_id": bound.snapshot_id,
            "authorization_graph_snapshot_id": current.snapshot_id,
            "frozen_content_digest": frozen_content,
            "authorization_content_digest": current_content,
            "source_choice": choice or "unchanged", "override": override}


def launch_work_stage(*, frozen, current, work_key, stage, store,
                      grant_ref, grant_authority, resolved_config,
                      choice=None, override=None, inputs=None, types=None,
                      outputs=None, now=None):
    """Require a host-provided grant authority before using the frozen stage."""
    binding = preflight(frozen, current, work_key, choice=choice,
                        override=override)
    if not callable(grant_authority) or not isinstance(grant_ref, str) or not grant_ref:
        raise LaunchError("grant_authority_required")
    grant = grant_authority(grant_ref, binding)
    if not isinstance(grant, dict) or grant.get("grant_id") != grant_ref:
        raise LaunchError("grant_invalid")
    if not grant.get("operator_authorized"):
        raise LaunchError("operator_not_authorized")
    if grant.get("work_key") != work_key:
        raise LaunchError("grant_wrong_work")
    if grant.get("graph_snapshot_id") != binding["selected_graph_snapshot_id"]:
        raise LaunchError("grant_wrong_graph")
    if grant.get("runner") != "langflow-local":
        raise LaunchError("grant_wrong_runner")
    if grant.get("scope") != "stage-launch":
        raise LaunchError("grant_wrong_scope")
    limits = grant.get("limits")
    if (not isinstance(limits, dict) or
            type(limits.get("timeout_seconds")) is not int or
            not 1 <= limits["timeout_seconds"] <= 3600 or
            type(limits.get("max_turns")) is not int or
            not 0 <= limits["max_turns"] <= 100):
        raise LaunchError("grant_limits_invalid")
    try:
        expiry = datetime.fromisoformat(grant["expires_at"])
        clock = now or datetime.now(timezone.utc)
        if expiry.tzinfo is None or expiry <= clock:
            raise LaunchError("grant_expired")
    except (KeyError, TypeError, ValueError):
        raise LaunchError("grant_expiry_invalid") from None
    config = dict(resolved_config)
    config["grant_ref"] = grant_ref
    config["effective_limits"] = limits
    return stage.execute(store, resolved_config=config,
                         trigger={"type": "selected-work", **binding},
                         inputs=inputs, types=types, outputs=outputs)
