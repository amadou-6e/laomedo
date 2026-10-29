"""Real production stage A; initialized zero-turn continuity fixture B."""

from laomedo.host.leases.models import ContainerIdentity
import argparse
import json
import os
from pathlib import Path
import time

from experiments.exp93.real_stage_support import identities; from experiments.exp93.real_stage_support import save; from experiments.exp93.real_stage_support import TASK
from laomedo.host.leases.utils import inspect_exact
from laomedo.agents.agents.codex.controller.service import CodexController as AppServer; from laomedo.agents.agents.codex.agent import CodexAgent as LocalRunner; from laomedo.agents.errors import RunnerError
from experiments.turn_harness import VerificationLocalRunner as LocalRunner
from laomedo.host.mediation.authority import RunGrantAuthority


def run(root, side):
    class Boundary(AppServer):
        def __init__(self, command, evidence, **kwargs):
            owner = json.loads((evidence / "record.json").read_bytes())["container_ownership"]
            capability = (root / "host/lease/leases" / owner["launch_token"] / "grant.secret").read_text().strip()
            super().__init__(command, evidence, secret_redactions=tuple(kwargs.pop("secret_redactions", ())) + (capability,), **kwargs)

        async def initialize(self):
            await super().initialize()
            selected = identities(root, side)
            state, container_id = inspect_exact(ContainerIdentity(name=selected['name'], run_id=selected['run_id'], token=selected['token']))
            if state != "owned":
                raise RunnerError("native_container_not_owned")
            save(root / (side + "-ready.json"), {**selected, "container_id": container_id,
                 "pid": os.getpid(), "initialize_confirmed": True})
            if side == "b":
                while not (root / "b-stop").exists():
                    if time.monotonic() >= float((root / "deadline").read_text()):
                        break
                    time.sleep(.1)
                raise RunnerError("zero_turn_control_finished")

    runner = LocalRunner(root / "runner", root / "skill-store", root / ("source-" + side),
        transport=Boundary, max_model_turns=1 if side == "a" else 0, git_workspace=True,
        supervise_containers=True, lease_service=root / "host/lease",
        github_authority=RunGrantAuthority(root / "host/authority.sqlite"),
        mediator_state=root / "host/mediator")
    save(root / (side + "-constructed.json"), {"pid": os.getpid(), "constructed": True})
    while not (root / "start-gate").exists():
        if time.monotonic() >= float((root / "deadline").read_text()):
            raise TimeoutError("dispatch_gate_deadline")
        time.sleep(.1)
    prepared = runner._prepare({"task": TASK, "model": "gpt-6-luna", "effort": "low",
        "skill_ref": json.loads((root / "skill-reference.json").read_bytes()),
        "github_authorization_ref": json.loads((root / (side + "-authorization.json")).read_bytes())})
    runner._execute(prepared["run_id"], TASK, resume=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--side", choices=("a", "b"), required=True)
    args = parser.parse_args()
    try:
        run(args.root.resolve(), args.side)
    except Exception as failure:
        print(json.dumps({"result": "worker_ended", "error_class": type(failure).__name__}))
        raise SystemExit(1)
