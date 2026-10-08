"""Independent credential-free lease and file-bridge host for Phase C only."""

import argparse
import json
from pathlib import Path
import time

from laomedo.file_mediation_bridge import FileMediationBridge
from laomedo.github_mediation import MediationStore
from laomedo.host_services import serve_services
from laomedo.lease_service import LeaseService
from laomedo.mediation_authority import RunGrantAuthority
from laomedo.mediation_service import MediationHTTPService


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--runner-runs-root", type=Path, required=True)
    args = parser.parse_args()
    state = args.state.resolve()
    runs = args.runner_runs_root.resolve()
    if not runs.is_dir() or not state.is_dir():
        parser.error("private_state_and_runner_runs_required")
    (state / "mediator").mkdir(exist_ok=True)
    store = MediationStore(state / "mediator" / "mediator.sqlite")
    authority = RunGrantAuthority(state / "authority.sqlite")
    lease = LeaseService(state / "lease", mediator=store,
                         mediation_authority=authority.authorize_lease)
    receipts = state / "mediator" / "fake-provider.jsonl"

    def fake_transport(repository, operation, payload, **_binding):
        if repository != "example/disposable" or operation != "pr_update" or \
                payload.get("number") not in (7, 8):
            raise RuntimeError("fake_provider_scope_mismatch")
        with receipts.open("a", encoding="utf-8") as output:
            output.write(json.dumps({"at_monotonic": time.monotonic(),
                                     "operation": operation,
                                     "number": payload["number"]}) + "\n")
        return {"synthetic": True, "number": payload["number"]}

    mediator = MediationHTTPService(store, fake_transport)
    bridge = FileMediationBridge(runs, state / "lease", store,
                                 fake_transport,
                                 state / "mediator" / "file-bridge-journal.jsonl")
    serve_services(lease, mediator, state, repository="example/disposable",
                   connection_id="synthetic", connection_generation=1,
                   file_bridge=bridge)


if __name__ == "__main__":
    main()
