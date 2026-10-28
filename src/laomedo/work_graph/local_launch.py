"""local launch helpers."""

from __future__ import annotations

from pathlib import Path
import json
import laomedo.agents.workflow.errors as _workflow_errors
import laomedo.agents.workflow.store as _workflow_store
import laomedo.work_graph.grant_utils as _work_graph_grant_utils
import laomedo.work_graph.grants as _work_graph_grants
import laomedo.work_graph.launch as _work_graph_launch
import laomedo.work_graph.models as _work_graph_models


def launch_local_saved_flow(
    *,
    snapshot_path,
    work_key,
    flow_id,
    langflow_base,
    grant_store,
    grant_ref,
    run_store,
    task,
    choice=None,
    source_root=None,
):
    import laomedo.work_graph.client as _work_graph_client

    frozen = _work_graph_models.GraphSnapshot.from_dict(
        json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    )
    authority = _work_graph_grants.LocalGrantAuthority(grant_store)
    run_path = _work_graph_grant_utils._private_path(run_store)
    if run_path == authority.path:
        raise _workflow_errors.LaunchError("run_and_grant_store_must_differ")
    store = _workflow_store.WorkflowRunStore(run_path)
    client = _work_graph_client.LangflowLocalClient(langflow_base)
    record, output = _work_graph_launch.launch_github_docker_saved_flow_stage(
        frozen=frozen,
        work_key=work_key,
        flow_id=flow_id,
        fetch_export=client.fetch,
        store=store,
        grant_ref=grant_ref,
        grant_authority=authority,
        resolved_config={"mode": "zero-turn-local"},
        choice=choice,
        inputs=[{"input_value": task}],
        types=["chat"],
        outputs=None,
        source_root=source_root,
    )
    return {
        "run_id": record["run_id"],
        "trace_id": record["trace_id"],
        "status": record["status"],
        "completion_basis": record["completion_basis"],
        "evidence_complete": bool(record["evidence_complete"]),
        "dispatch_attempts": record["dispatch_attempts"],
        "output_present": bool(output),
        "graph_revision": record["graph_revision"],
    }
