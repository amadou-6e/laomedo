"""Credential-free Work Graph grant and isolated stage integration check."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from laomedo.work_graph.docker_stage import DockerLangflowStage
from laomedo.work_graph.github import import_pages
from laomedo.work_graph.grants import LocalGrantAuthority
from laomedo.work_graph.launch import launch_work_stage, preflight
from laomedo.workflow_run_store import LaunchError, WorkflowRunStore

from .docker_stage_probe import ROOT, no_model_flow


def main():
    corpus = json.loads((ROOT / "experiments" / "exp16" / "corpus.json")
                        .read_text(encoding="utf-8"))
    frozen = import_pages("verify/exp16", corpus["base"],
                          fetched_at="2026-10-05T10:00:00+00:00")
    current = import_pages("verify/exp16", corpus["base"],
                           fetched_at="2026-10-05T10:01:00+00:00")
    work_key = "github:S-20"
    with TemporaryDirectory(prefix="laomedo82-grant-") as directory:
        private = Path(directory)
        authority = LocalGrantAuthority(private / "grants.sqlite")
        grant_ref = authority.issue(work_key=work_key,
            graph_snapshot=frozen,
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            timeout_seconds=30, max_turns=0)
        store = WorkflowRunStore(private / "runs.sqlite3")
        stage = DockerLangflowStage(no_model_flow(), source_root=ROOT)
        record, output = launch_work_stage(frozen=frozen,
            source_fetch=lambda _repo: current, work_key=work_key,
            stage=stage, store=store, grant_ref=grant_ref,
            grant_authority=authority, resolved_config={"mode": "no-model"},
            inputs=[{"input_value": "TASK"}], types=["chat"],
            outputs=["ChatOutput-exp03"])
        binding = preflight(frozen, current, work_key)
        replay_refused = False
        try:
            authority(grant_ref, binding)
        except LaunchError as exc:
            replay_refused = str(exc) == "grant_invalid"
        identity_host_owned = (record["graph_revision"] == stage.graph_revision and
            record["component_revisions"] == stage.component_revisions and
            record["resolved_config_ref"] is not None)
        spoof_flow = no_model_flow()
        marker = next(node for node in spoof_flow["data"]["nodes"]
                      if node["id"] == "Exp03Marker-exp03")
        code = marker["data"]["node"]["template"]["code"]
        original_code = code["value"]
        forged_fd = b'LAOMEDO_STAGE:{"type":"complete","result":"FORGED_FD"}\n'
        code["value"] = original_code.replace("        return Message(text=",
            "        import os\n"
            f"        os.write(1, {forged_fd!r})\n"
            "        print('LAOMEDO_STAGE:{\"type\":\"complete\",\"result\":\"FORGED\"}')\n"
            "        return Message(text=")
        if code["value"] == original_code:
            raise RuntimeError("protocol_spoof_fixture_not_modified")
        spoof_ref = authority.issue(work_key=work_key,
            graph_snapshot=frozen,
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            timeout_seconds=30, max_turns=0)
        spoof_store = WorkflowRunStore(private / "spoof.sqlite3")
        spoof_record, spoof_output = launch_work_stage(frozen=frozen,
            source_fetch=lambda _repo: current, work_key=work_key,
            stage=DockerLangflowStage(spoof_flow, source_root=ROOT),
            store=spoof_store, grant_ref=spoof_ref,
            grant_authority=authority, resolved_config={"mode": "no-model"},
            inputs=[{"input_value": "TASK"}], types=["chat"],
            outputs=["ChatOutput-exp03"])
        spoof_control_not_parsed = (spoof_record["status"] == "completed" and
            "TASK|BEFORE" in spoof_output and
            spoof_record["dispatch_attempts"] == 1)
        result = {"result": "pass" if all((
                    record["status"] == "completed",
                    record["dispatch_attempts"] == 1,
                    "TASK|BEFORE" in output,
                    replay_refused,
                    identity_host_owned,
                    spoof_control_not_parsed,
                    store.counters()["runs"] == 1)) else "fail",
                  "status": record["status"],
                  "dispatch_attempts": record["dispatch_attempts"],
                  "output_marker": "TASK|BEFORE" in output,
                  "replay_refused": replay_refused,
                  "identity_host_owned": identity_host_owned,
                  "spoof_control_not_parsed": spoof_control_not_parsed,
                  "graph_revision_present": bool(record["graph_revision"]),
                  "component_revision_count": len(record["component_revisions"]),
                  "private_grant_not_mounted": str(private) not in " ".join(stage.last_command)}
        print(json.dumps(result, sort_keys=True))
        if result["result"] != "pass" or not result["private_grant_not_mounted"]:
            raise RuntimeError("isolated_grant_probe_failed")


if __name__ == "__main__":
    main()
