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


class HeldAgentRequestBridge(FileMediationBridge):
    """Test-only barrier for one already-claimed agent request."""

    def __init__(self, *args, held_effect: str, barrier: Path, **kwargs):
        super().__init__(*args, **kwargs)
        self.held_effect = held_effect
        self.barrier = barrier

    def _process(self, run_id, effect_id, claimed, responses, token):
        if effect_id == self.held_effect:
            self.barrier.write_text(json.dumps({
                "run_id": run_id, "effect_id": effect_id,
                "claimed_name": claimed.name,
                "held_at_monotonic": time.monotonic(),
            }), encoding="utf-8")
            deadline = time.monotonic() + 70
            while time.monotonic() < deadline:
                for lease_dir in (self.lease_root / "leases").glob("*/lease.json"):
                    try:
                        lease = json.loads(lease_dir.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        continue
                    if (lease.get("run_id") == run_id and
                            (lease_dir.parent / "revoked.json").exists()):
                        return super()._process(
                            run_id, effect_id, claimed, responses, token)
                time.sleep(.05)
            raise RuntimeError("held_agent_request_revocation_timeout")
        return super()._process(run_id, effect_id, claimed, responses, token)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--runner-runs-root", type=Path, required=True)
    parser.add_argument("--hold-agent-effect")
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
    bridge_args = (runs, state / "lease", store, fake_transport,
                   state / "mediator" / "file-bridge-journal.jsonl")
    bridge = (HeldAgentRequestBridge(
        *bridge_args, held_effect=args.hold_agent_effect,
        barrier=state / "mediator" / "held-agent-request.json")
        if args.hold_agent_effect else FileMediationBridge(*bridge_args))
    serve_services(lease, mediator, state, repository="example/disposable",
                   connection_id="synthetic", connection_generation=1,
                   file_bridge=bridge)


if __name__ == "__main__":
    main()
