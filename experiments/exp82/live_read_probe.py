"""Read-only GitHub refresh probe; no grant, reservation or stage dispatch."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from laomedo.work_graph.github import fetch
from laomedo.work_graph.launch import launch_github_work_stage, preflight
from laomedo.workflow_run_store import LaunchError, WorkflowRunStore


REPOSITORY = "amadou-6e/laomedo"
ISSUE_NUMBER = 82


class DispatchTrap:
    def execute(self, *_args, **_kwargs):
        raise AssertionError("the probe must never dispatch a stage")


def main():
    frozen = fetch(REPOSITORY)
    selected = next(item for item in frozen.items if item.number == ISSUE_NUMBER)
    with TemporaryDirectory(prefix="laomedo82-") as directory:
        store = WorkflowRunStore(Path(directory) / "runs.sqlite3")
        outcome = None
        try:
            launch_github_work_stage(frozen=frozen, work_key=selected.key,
                stage=DispatchTrap(), store=store, grant_ref="synthetic",
                grant_authority=None, resolved_config={"mode": "no-model"})
        except LaunchError as exc:
            outcome = str(exc)
        if outcome not in {"grant_authority_required", "stale_unacknowledged"}:
            raise RuntimeError("unexpected_live_preflight_outcome: " + str(outcome))
        if store.counters()["runs"] != 0 or store.counters()["dispatch_attempts"] != 0:
            raise RuntimeError("unexpected_live_reservation_or_dispatch")
        current = fetch(REPOSITORY)
        result = {"repository": REPOSITORY,
            "source_complete": frozen.source_complete and current.source_complete,
            "snapshot_ids_differ": frozen.snapshot_id != current.snapshot_id,
            "launch_refusal": outcome,
            "zero_reservations": True, "zero_dispatch_attempts": True}
        try:
            decision = preflight(frozen, current, selected.key)
        except LaunchError as exc:
            result["comparison_refusal"] = str(exc)
        else:
            result["source_choice"] = decision["source_choice"]
            result["relevant_content_same"] = (decision["frozen_content_digest"] ==
                                               decision["authorization_content_digest"])
            result["bound_and_authorization_ids_distinct"] = (
                decision["selected_graph_snapshot_id"] !=
                decision["authorization_graph_snapshot_id"])
        print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
