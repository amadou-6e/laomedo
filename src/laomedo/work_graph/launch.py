"""Fail-closed Work Graph checks before a Langflow stage reserves a run."""

from datetime import datetime
from datetime import timezone
from hashlib import sha256
import json
import laomedo.work_graph.runs.errors as _workflow_errors
import laomedo.work_graph.models as _work_graph_models


def _digest(value):
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return "sha256:" + sha256(encoded).hexdigest()


def _item(graph, key):
    return next((item for item in graph.items if item.key == key), None)


def relevant_content_digest(
    graph: _work_graph_models.GraphSnapshot, work_key: str
) -> str:
    """Hash selected work and its transitive prerequisites, excluding fetch time."""
    if not isinstance(graph, _work_graph_models.GraphSnapshot) or not isinstance(
        work_key, str
    ):
        raise _workflow_errors.LaunchError("invalid_work_graph")
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
    relevant_edges = sorted(
        (edge.model_dump() for edge in graph.dependencies if edge.dependent in seen),
        key=lambda edge: json.dumps(edge, sort_keys=True, ensure_ascii=False),
    )
    return _digest(
        {
            "repository": graph.repository,
            "schema_version": graph.schema_version,
            "connector_version": graph.connector_version,
            "source_complete": graph.source_complete,
            "items": [items[key].model_dump() for key in sorted(seen) if key in items],
            "unresolved_keys": sorted(seen - items.keys()),
            "edges": relevant_edges,
        }
    )


def preflight(
    frozen: _work_graph_models.GraphSnapshot,
    current: _work_graph_models.GraphSnapshot,
    work_key: str,
    *,
    choice=None,
    override=None,
) -> dict:
    if (
        not isinstance(frozen, _work_graph_models.GraphSnapshot)
        or not isinstance(current, _work_graph_models.GraphSnapshot)
        or frozen.repository != current.repository
    ):
        raise _workflow_errors.LaunchError("invalid_work_graph")
    if not current.source_complete:
        raise _workflow_errors.LaunchError("source_incomplete")
    selected = _item(current, work_key)
    if selected is None or selected.state != "OPEN":
        raise _workflow_errors.LaunchError("selected_item_unavailable")
    original = _item(frozen, work_key)
    if original is None:
        raise _workflow_errors.LaunchError("frozen_item_unavailable")
    frozen_content = relevant_content_digest(frozen, work_key)
    current_content = relevant_content_digest(current, work_key)
    changed = frozen_content != current_content
    if changed and choice not in {"pinned", "refreshed"}:
        raise _workflow_errors.LaunchError("stale_unacknowledged")
    if choice not in {None, "pinned", "refreshed"}:
        raise _workflow_errors.LaunchError("invalid_source_choice")
    readiness = current.readiness().get(work_key)
    if readiness in {"unknown", "cyclic"}:
        raise _workflow_errors.LaunchError("prerequisite_" + readiness)
    if readiness == "blocked":
        open_edges = {
            (edge.prerequisite, edge.dependent)
            for edge in current.dependencies
            if edge.dependent == work_key
            and (blocker := _item(current, edge.prerequisite)) is not None
            and blocker.state == "OPEN"
        }
        if (
            not isinstance(override, dict)
            or set(override) != {"prerequisite", "dependent", "rationale"}
            or not isinstance(override["rationale"], str)
            or not override["rationale"].strip()
            or open_edges != {(override["prerequisite"], override["dependent"])}
        ):
            raise _workflow_errors.LaunchError("open_prerequisite")
    elif readiness != "ready" or override is not None:
        raise _workflow_errors.LaunchError("override_not_applicable")
    bound = current if choice == "refreshed" else frozen
    if not bound.source_complete:
        raise _workflow_errors.LaunchError("bound_source_incomplete")
    bound_item = _item(bound, work_key)
    if bound_item is None or bound_item.state != "OPEN":
        raise _workflow_errors.LaunchError("bound_item_unavailable")
    work = {
        "key": bound_item.key,
        "repository": bound_item.repository,
        "number": bound_item.number,
        "url": bound_item.url,
        "updated_at": bound_item.updated_at,
        "body_digest": _digest(bound_item.body),
    }
    return {
        "work_snapshot": work,
        "work_snapshot_id": _digest(work),
        "input_digest": _digest(
            {
                "work": work,
                "body": bound_item.body,
                "graph_snapshot_id": bound.snapshot_id,
            }
        ),
        "selected_graph_snapshot_id": bound.snapshot_id,
        "authorization_graph_snapshot_id": current.snapshot_id,
        "selected_content_digest": (
            current_content if choice == "refreshed" else frozen_content
        ),
        "frozen_content_digest": frozen_content,
        "authorization_content_digest": current_content,
        "source_choice": choice or "unchanged",
        "override": override,
    }


def launch_work_stage(
    *,
    frozen,
    source_fetch,
    work_key,
    stage,
    store,
    grant_ref,
    grant_authority,
    resolved_config,
    choice=None,
    override=None,
    inputs=None,
    types=None,
    outputs=None,
    now=None,
):
    """Refresh source at launch, then require a host-provided grant authority."""
    if not isinstance(frozen, _work_graph_models.GraphSnapshot) or not callable(
        source_fetch
    ):
        raise _workflow_errors.LaunchError("source_refresh_required")
    current = source_fetch(frozen.repository)
    binding = preflight(frozen, current, work_key, choice=choice, override=override)
    if not callable(grant_authority) or not isinstance(grant_ref, str) or not grant_ref:
        raise _workflow_errors.LaunchError("grant_authority_required")
    grant = grant_authority(grant_ref, binding)
    if not isinstance(grant, dict) or grant.get("grant_id") != grant_ref:
        raise _workflow_errors.LaunchError("grant_invalid")
    if not grant.get("operator_authorized"):
        raise _workflow_errors.LaunchError("operator_not_authorized")
    if grant.get("work_key") != work_key:
        raise _workflow_errors.LaunchError("grant_wrong_work")
    if grant.get("content_digest") != binding["selected_content_digest"]:
        raise _workflow_errors.LaunchError("grant_wrong_content")
    if grant.get("runner") != "langflow-local":
        raise _workflow_errors.LaunchError("grant_wrong_runner")
    if grant.get("scope") != "stage-launch":
        raise _workflow_errors.LaunchError("grant_wrong_scope")
    limits = grant.get("limits")
    if (
        not isinstance(limits, dict)
        or type(limits.get("timeout_seconds")) is not int
        or not 1 <= limits["timeout_seconds"] <= 3600
        or type(limits.get("max_turns")) is not int
        or not 0 <= limits["max_turns"] <= 100
    ):
        raise _workflow_errors.LaunchError("grant_limits_invalid")
    try:
        expiry = datetime.fromisoformat(grant["expires_at"])
        clock = now or datetime.now(timezone.utc)
        if expiry.tzinfo is None or expiry <= clock:
            raise _workflow_errors.LaunchError("grant_expired")
    except (KeyError, TypeError, ValueError):
        raise _workflow_errors.LaunchError("grant_expiry_invalid") from None
    config = dict(resolved_config)
    config["grant_ref"] = grant_ref
    config["grant_reviewed_graph_snapshot_id"] = grant.get("graph_snapshot_id")
    config["effective_limits"] = limits
    return stage.execute(
        store,
        resolved_config=config,
        trigger={"type": "selected-work", **binding},
        inputs=inputs,
        types=types,
        outputs=outputs,
    )


def launch_github_work_stage(
    *,
    frozen,
    work_key,
    stage,
    store,
    grant_ref,
    grant_authority,
    resolved_config,
    choice=None,
    override=None,
    inputs=None,
    types=None,
    outputs=None,
    now=None,
):
    """Use the production read-only GitHub connector for the final recheck."""
    import laomedo.work_graph.github as _work_graph_github

    return launch_work_stage(
        frozen=frozen,
        source_fetch=_work_graph_github.fetch,
        work_key=work_key,
        stage=stage,
        store=store,
        grant_ref=grant_ref,
        grant_authority=grant_authority,
        resolved_config=resolved_config,
        choice=choice,
        override=override,
        inputs=inputs,
        types=types,
        outputs=outputs,
        now=now,
    )


def launch_github_saved_flow_stage(
    *,
    frozen,
    work_key,
    flow_id,
    fetch_export,
    store,
    grant_ref,
    grant_authority,
    resolved_config,
    choice=None,
    override=None,
    inputs=None,
    types=None,
    outputs=None,
    now=None,
):
    """Build one saved-flow revision and pass it through the Work Graph gate."""
    import laomedo.integrations.langflow.stage_adapter as _langflow_stage_adapter

    stage = _langflow_stage_adapter.FrozenLangflowStage.from_saved_flow(
        flow_id, fetch_export
    )
    return launch_github_work_stage(
        frozen=frozen,
        work_key=work_key,
        stage=stage,
        store=store,
        grant_ref=grant_ref,
        grant_authority=grant_authority,
        resolved_config=resolved_config,
        choice=choice,
        override=override,
        inputs=inputs,
        types=types,
        outputs=outputs,
        now=now,
    )


def launch_github_docker_saved_flow_stage(
    *,
    frozen,
    work_key,
    flow_id,
    fetch_export,
    store,
    grant_ref,
    grant_authority,
    resolved_config,
    choice=None,
    override=None,
    inputs=None,
    types=None,
    outputs=None,
    source_root=None,
    now=None,
):
    """Keep the grant on the host and execute the frozen flow in Docker."""
    import laomedo.work_graph.docker_stage as _work_graph_docker_stage

    stage = _work_graph_docker_stage.DockerLangflowStage.from_saved_flow(
        flow_id, fetch_export, source_root=source_root
    )
    return launch_github_work_stage(
        frozen=frozen,
        work_key=work_key,
        stage=stage,
        store=store,
        grant_ref=grant_ref,
        grant_authority=grant_authority,
        resolved_config=resolved_config,
        choice=choice,
        override=override,
        inputs=inputs,
        types=types,
        outputs=outputs,
        now=now,
    )
