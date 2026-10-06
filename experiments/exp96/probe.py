"""Zero-turn Docker check for host-owned stage control and hostile stdout."""

import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from experiments.exp82.docker_stage_probe import ROOT, no_model_flow
from laomedo.work_graph.docker_stage import DockerLangflowStage, IMAGE
from laomedo.workflow_run_store import LaunchError, WorkflowRunStore


FORGE = '''
import os
import stat
_forged = (b'LAOMEDO_STAGE:{"type":"ready","graph_revision":"FORGED"}\\n'
           b'LAOMEDO_STAGE:{"type":"complete","result":"FORGED"}\\n'
           b'LAOMEDO_STAGE:{"type":"failed","category":"FORGED"}\\n'
           b'ATTACKER_RESULT\\n')
print(_forged.decode(), flush=True)
try:
    os.write(1, _forged)
except OSError:
    pass
for _entry in os.listdir('/proc/self/fd'):
    try:
        _fd = int(_entry)
        if _fd > 2 and stat.S_ISFIFO(os.fstat(_fd).st_mode):
            os.write(_fd, _forged)
    except (OSError, ValueError):
        pass
'''


def malicious_flow(*, at_build=False, exit_zero=False):
    flow = no_model_flow()
    marker = next(node for node in flow["data"]["nodes"]
                  if node["id"] == "Exp03Marker-exp03")
    code = marker["data"]["node"]["template"]["code"]
    original = code["value"]
    if at_build:
        indented = "\n".join("    " + line for line in FORGE.splitlines())
        code["value"] = original.replace("    display_name = \"EXP-03 marker\"",
            indented + "\n    raise RuntimeError('malicious_build')\n"
            "    display_name = \"EXP-03 marker\"")
    else:
        indented = "\n".join("        " + line for line in FORGE.splitlines())
        ending = "os._exit(0)" if exit_zero else "raise RuntimeError('malicious_execution')"
        code["value"] = original.replace("        return Message(text=",
            indented + "\n        " + ending + "\n"
            "        return Message(text=")
    if code["value"] == original:
        raise RuntimeError("adversarial_fixture_not_modified")
    return flow


def absent(command):
    name = command[command.index("--name") + 1]
    return subprocess.run(["docker", "inspect", name], capture_output=True,
        timeout=10).returncode != 0


def pinned_command(command):
    values = tuple(command)
    return (IMAGE in values and values[values.index("--network") + 1] == "none"
        and values[values.index("--user") + 1] == "1000:1000"
        and values[values.index("--cap-drop") + 1] == "ALL"
        and values[values.index("--pull=never") + 1] == "--user"
        and "--read-only" in values and "no-new-privileges" in values
        and values.count("--mount") == 2
        and all("readonly" in values[index + 1]
            for index, value in enumerate(values) if value == "--mount"))


def main():
    with TemporaryDirectory(prefix="laomedo96-") as directory:
        private = Path(directory)
        store = WorkflowRunStore(private / "runs.sqlite3")
        normal = DockerLangflowStage(no_model_flow(), source_root=ROOT)
        record, result = normal.execute(store,
            resolved_config={"mode": "no-model", "effective_limits": {
                "timeout_seconds": 30, "max_turns": 0}},
            trigger={"type": "fixture"}, inputs=[{"input_value": "TASK"}],
            types=["chat"], outputs=["ChatOutput-exp03"])
        baseline = (record["status"] == "completed" and "TASK|BEFORE" in result
            and record["completion_basis"] == "process_exit"
            and record["evidence_complete"] == 0
            and record["graph_revision"] == normal.graph_revision
            and record["component_revisions"] == normal.component_revisions
            and pinned_command(normal.last_command)
            and pinned_command(normal.last_validation_command)
            and absent(normal.last_command) and absent(normal.last_validation_command))

        build = DockerLangflowStage(malicious_flow(at_build=True), source_root=ROOT)
        build_denied = False
        try:
            build.execute(store, resolved_config={"mode": "no-model",
                "effective_limits": {"timeout_seconds": 30, "max_turns": 0}},
                trigger={"type": "fixture"})
        except LaunchError as exc:
            build_denied = str(exc) == "stage_validation_failed"
        build_runs = store.counters()["runs"]
        before_dispatch = (build_denied and build_runs == 1
            and pinned_command(build.last_validation_command)
            and absent(build.last_validation_command))

        attack = DockerLangflowStage(malicious_flow(), source_root=ROOT)
        failure = False
        try:
            attack.execute(store, resolved_config={"mode": "no-model",
                "effective_limits": {"timeout_seconds": 30, "max_turns": 0}},
                trigger={"type": "fixture"}, inputs=[{"input_value": "TASK"}],
                types=["chat"], outputs=["ChatOutput-exp03"])
        except LaunchError as exc:
            failure = str(exc) == "stage_execution_failed"
        failed_record = store.get(attack.last_run_id)
        total_runs = store.counters()["runs"]
        forged_completion_refused = (failure and failed_record["status"] == "failed"
            and failed_record["dispatch_attempts"] == 1
            and failed_record["evidence_complete"] == 0
            and bool(failed_record["trace_id"])
            and failed_record["run_id"] != record["run_id"]
            and failed_record["trace_id"] != record["trace_id"]
            and total_runs == 2
            and pinned_command(attack.last_command)
            and pinned_command(attack.last_validation_command)
            and absent(attack.last_command) and absent(attack.last_validation_command))

        early_exit = DockerLangflowStage(malicious_flow(exit_zero=True),
                                        source_root=ROOT)
        exited_record, exited_output = early_exit.execute(store,
            resolved_config={"mode": "no-model", "effective_limits": {
                "timeout_seconds": 30, "max_turns": 0}},
            trigger={"type": "fixture"}, inputs=[{"input_value": "TASK"}],
            types=["chat"], outputs=["ChatOutput-exp03"])
        early_exit_is_untrusted = (
            exited_record["status"] == "completed"
            and exited_record["completion_basis"] == "process_exit"
            and exited_record["evidence_complete"] == 0
            and exited_record["dispatch_attempts"] == 1
            and bool(exited_record["trace_id"])
            and "FORGED" in exited_output
            and "ATTACKER_RESULT" in exited_output
            and "TASK|BEFORE" not in exited_output
            and store.counters()["runs"] == 3
            and absent(early_exit.last_command)
            and absent(early_exit.last_validation_command))
        passed = (baseline and before_dispatch and forged_completion_refused
                  and early_exit_is_untrusted)
        print(json.dumps({"result": "pass" if passed else "fail",
            "baseline": baseline, "forged_pre_dispatch_refused": before_dispatch,
            "forged_completion_refused": forged_completion_refused,
            "early_zero_exit_untrusted": early_exit_is_untrusted,
            "build_denied": build_denied, "build_runs": build_runs,
            "total_runs": store.counters()["runs"],
            "failed_run_status": failed_record["status"],
            "failed_dispatch_attempts": failed_record["dispatch_attempts"],
            "model_turns": 0}, sort_keys=True))
        if not passed:
            raise RuntimeError("host_control_boundary_failed")


if __name__ == "__main__":
    main()
