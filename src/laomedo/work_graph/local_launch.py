"""local launch helpers."""

from __future__ import annotations

from pathlib import Path
import json
from laomedo.work_graph.runs.errors import LaunchError
from laomedo.work_graph.runs.store import WorkflowRunStore
from laomedo.work_graph.grant_utils import _private_path
from laomedo.work_graph.grants import LocalGrantAuthority
from laomedo.work_graph.launch import launch_github_docker_saved_flow_stage
from laomedo.work_graph.models import GraphSnapshot


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
    from laomedo.work_graph.client import LangflowLocalClient

    frozen = GraphSnapshot.from_dict(
        json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    )
    authority = LocalGrantAuthority(grant_store)
    run_path = _private_path(run_store)
    if run_path == authority.path:
        raise LaunchError("run_and_grant_store_must_differ")
    store = WorkflowRunStore(run_path)
    client = LangflowLocalClient(langflow_base)
    record, output = launch_github_docker_saved_flow_stage(
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
