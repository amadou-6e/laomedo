"""Single-use, independently reviewed real-agent crash test. No GitHub writes."""

from laomedo.host.leases.models import ContainerIdentity
import argparse
from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib import error; from urllib import request

from experiments.exp93.real_stage_support import IDENTITY; from experiments.exp93.real_stage_support import TASK; from experiments.exp93.real_stage_support import identities; from experiments.exp93.real_stage_support import reserve; from experiments.exp93.real_stage_support import finalize; from experiments.exp93.real_stage_support import save; from experiments.exp93.real_stage_support import validate
from experiments.exp104 import native_managed_tasks as tasks
from experiments.exp104.native_localrunner_probe import api; from experiments.exp104.native_localrunner_probe import git; from experiments.exp104.native_localrunner_probe import wait_json; from experiments.exp104.native_localrunner_probe import readiness; from experiments.exp104.native_localrunner_probe import journal; from experiments.exp104.native_localrunner_probe import scan_owned; from experiments.exp104.native_localrunner_probe import configure_owned_clone
from experiments.exp104.probe_active_delivery import stage_cleanup
from laomedo.host.leases.utils import cleanup_exact; from laomedo.host.leases.utils import inspect_exact
from laomedo.github.transport.git.utils import _base_git_environment
from laomedo.host.mediation.store import MediationStore
from laomedo.github.transport.rest.transport import _NoRedirect
from laomedo.host.credentials.token.connection import HostTokenConnection
from laomedo.agents.agents.codex.settings import GIT_IMAGE_ID; from laomedo.agents.agents.codex.runner import CodexRunner as LocalRunner
from experiments.turn_harness import VerificationLocalRunner as LocalRunner
from laomedo.host.mediation.authority import RunGrantAuthority
from laomedo.skills.registry.store import SkillStore

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "ga84jog/laomedo-exp104-disposable-20261007"
BASELINE = "1f1a505f2fbd31993a7946924a9bec5a27bb15c1"
SPEC = "be233d7a452dc4a5b66e1ede4d15da9e3b41bcf6"
LEDGER = Path.home() / "AppData/Local/Laomedo/exp22-phase-c-turns.json"


def phase(root, observation, name):
    if time.monotonic() >= float((root/"deadline").read_text()):
        raise TimeoutError("overall_procedure_deadline")
    observation["phase"] = name
    save(root/"observation.json",observation)


def wait_cleanup(root, selected, killed):
    deadline = min(killed+60,float((root/"deadline").read_text()))
    path = root/"host/lease/leases"/selected["token"]/"result.json"
    while time.monotonic()<deadline:
        if path.exists():
            result = json.loads(path.read_bytes())
            finished = result.get("cleanup_finished_at_monotonic")
            if result.get("cleanup_verified") is not True or type(finished) not in (float,int) or not killed<=finished<=killed+60:
                raise ValueError("service_cleanup_unverified_or_late")
            if inspect_exact(ContainerIdentity(name=selected['name'], run_id=selected['run_id'], token=selected['token']))[0] != "absent":
                raise ValueError("independent_container_absence_failed")
            observed = time.monotonic()
            if observed>killed+60:
                raise ValueError("independent_cleanup_observation_late")
            return finished,observed
        time.sleep(.05)
    raise TimeoutError("service_cleanup_deadline")


def mediate(mediator, capability, operation, payload):
    body = {"repository": REPOSITORY, "operation": operation, "payload": payload}
    if operation == "pr_create":
        body["effect_id"] = IDENTITY + "-denied-pr"
    call = request.Request(f"http://127.0.0.1:{mediator['port']}/v1/mediate",
        data=json.dumps(body).encode(), method="POST", headers={
            "Authorization": "Bearer " + capability, "Content-Type": "application/json",
            "X-Laomedo-Mediator-Instance": mediator["instance"]})
    try:
        with request.build_opener(_NoRedirect).open(call, timeout=15) as response:
            return response.status, json.load(response)
    except error.HTTPError as failure:
        return failure.code, json.load(failure)


def inspect_target(target):
    response = subprocess.run(["docker", "inspect", target], capture_output=True,
                              text=True, timeout=10)
    if response.returncode:
        if "No such object:" in response.stderr or "No such container:" in response.stderr:
            return None
        raise ValueError("docker_inspection_unknown")
    try:
        entries = json.loads(response.stdout)
        if len(entries) != 1 or not isinstance(entries[0], dict):
            raise ValueError()
        return entries[0]
    except (ValueError, TypeError, IndexError):
        raise ValueError("docker_inspection_unknown") from None


def exact_container_state(selected, original_id):
    """Controller-owned witness; name absence alone cannot prove ID absence."""
    original = inspect_target(original_id)
    reserved = inspect_target(selected["name"])
    for entry in (original, reserved):
        if entry is None:
            continue
        labels = (entry.get("Config") or {}).get("Labels") or {}
        if (entry.get("Id") != original_id or
                entry.get("Name", "").lstrip("/") != selected["name"] or
                labels.get("laomedo.run_id") != selected["run_id"] or
                labels.get("laomedo.launch_token") != selected["token"]):
            raise ValueError("docker_identity_conflict")
    listed = subprocess.run(["docker", "ps", "-aq", "--no-trunc",
        "--filter", "label=laomedo.run_id="+selected["run_id"],
        "--filter", "label=laomedo.launch_token="+selected["token"]],
        capture_output=True, text=True, timeout=10)
    if listed.returncode:
        raise ValueError("docker_inspection_unknown")
    ids = listed.stdout.split()
    if any(value != original_id for value in ids):
        raise ValueError("docker_identity_conflict")
    absent = original is None and reserved is None and not ids
    running = (original is not None and reserved is not None and ids == [original_id]
        and (original.get("State") or {}).get("Running") is True
        and (reserved.get("State") or {}).get("Running") is True)
    checks = {"original_id": "absent" if original is None else "present",
              "reserved_name": "absent" if reserved is None else "present", "label_ids": ids}
    return absent, running, checks


def wait_exact_absence(root, selected, original_id, killed, observation):
    deadline = min(killed+60, float((root/"deadline").read_text()))
    path = root/"host/lease/leases"/selected["token"]/"result.json"
    while time.monotonic() < deadline:
        absent, _, checks = exact_container_state(selected, original_id)
        observed = time.monotonic()
        if observed > deadline:
            raise ValueError("independent_cleanup_observation_late")
        observation["loss"]["absence_checks"] = checks
        if absent and "container_absent_observed" not in observation["loss"]:
            observation["loss"]["container_absent_observed"] = observed
        if path.exists():
            service = json.loads(path.read_bytes())
            observation["loss"]["service_cleanup_state"] = service.get("state")
            observation["loss"]["service_cleanup_verified"] = service.get("cleanup_verified")
            observation["loss"]["service_cleanup_finished"] = service.get("cleanup_finished_at_monotonic")
            save(root/"observation.json", observation)
            if service.get("state") not in {"never_observed", "removed_after_loss"}:
                raise ValueError("service_cleanup_danger_signal")
            if absent:
                return
        save(root/"observation.json", observation)
        time.sleep(.05)
    raise TimeoutError("service_cleanup_deadline")


def kill(worker, ready, root):
    if worker.poll() is not None or worker.pid == os.getpid():
        raise ValueError("runner_not_alive")
    tasks.powershell("$p = Get-CimInstance Win32_Process -Filter " +
        tasks.quote("ProcessId=" + str(ready["pid"])) +
        "; if (-not $p -or -not $p.CommandLine.Contains('exp93.real_stage_worker') "
        "-or -not $p.CommandLine.Contains(" + tasks.quote(str(root)) + ") "
        "-or -not $p.CommandLine.Contains('--side a') "
        "-or ($p.ProcessId -ne " + str(worker.pid) + " -and $p.ParentProcessId -ne " +
        str(worker.pid) + ")) { throw 'runner_identity_changed' }")
    result = subprocess.run(["taskkill", "/PID", str(worker.pid), "/T", "/F"],
                            capture_output=True, timeout=10)
    if result.returncode:
        raise ValueError("kill_outcome_unknown")
    worker.wait(timeout=10)
    return time.monotonic()


def cleanup(root, owned, workers):
    result = {}
    dispatched = (root/"start-gate").exists()
    dbpath = root / "host/mediator/mediator.sqlite"
    try:
        store = MediationStore(dbpath) if dbpath.exists() else None
        if store:
            for side in ("a", "b"):
                selected = identities(root, side)
                if selected.get("run_id"):
                    store.revoke_run(selected["run_id"])
            with closing(store._connect()) as db:
                result["grants"] = not db.execute("SELECT 1 FROM grants WHERE revoked_at IS NULL").fetchone()
        else:
            result["grants"] = not dispatched
    except Exception:
        result["grants"] = False
    for side in ("a", "b"):
        try:
            selected = identities(root, side)
            if selected.get("name"):
                result[side], _ = cleanup_exact(ContainerIdentity(name=selected['name'], run_id=selected['run_id'], token=selected['token']))
            else:
                result[side] = not dispatched
        except Exception:
            result[side] = False
    try:
        result["stages"] = stage_cleanup(root / "stages", None)[0] if (root / "stages").exists() else not dispatched
    except Exception:
        result["stages"] = False
    (root / "b-stop").touch()
    result["workers"] = True
    for worker in workers.values():
        try:
            if worker.poll() is None:
                worker.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                subprocess.run(["taskkill", "/PID", str(worker.pid), "/T", "/F"],
                               capture_output=True, timeout=10, check=True)
                worker.wait(timeout=10)
            except Exception:
                result["workers"] = False
    try:
        result["tasks"] = all(tasks.cleanup(owned).values())
    except Exception:
        result["tasks"] = False
    return result


def run(root, token_file, source, review_file):
    root = root.resolve()
    if os.name != "nt" or root.name != IDENTITY or root.exists() or any(
            (p / ".git").exists() for p in root.parents):
        raise ValueError("fresh_outside_git_windows_state_required")
    if git("rev-parse", "HEAD") != source or git("status", "--porcelain", "--untracked-files=all"):
        raise ValueError("source_must_be_frozen_clean")
    review = json.loads(review_file.read_bytes())
    protocol_hash = sha256((ROOT/"experiments/exp93/REAL-STAGE-S3-PROTOCOL.md").read_bytes()).hexdigest()
    if (review.get("identity") != IDENTITY or review.get("source_sha") != source or review.get("verdict") != "approve"
            or review.get("protocol_sha256") != protocol_hash or review.get("spec_sha") != SPEC):
        raise ValueError("independent_pre_run_review_required")
    root.mkdir(parents=True)
    (root / "single-use.claim").touch(exist_ok=False)
    (root / "deadline").write_text(str(time.monotonic()+600), encoding="ascii")
    observation = {"identity": IDENTITY, "source_sha": source, "spec_sha": SPEC,
        "protocol_sha256": protocol_hash,
        "amendment_sha256": sha256((ROOT/"experiments/exp93/REAL-STAGE-AMENDMENT-01.md").read_bytes()).hexdigest(),
        "task_sha256": sha256(TASK.encode()).hexdigest(), "review_sha256": sha256(review_file.read_bytes()).hexdigest(),
        "image_id": GIT_IMAGE_ID, "model": "gpt-6-luna", "effort": "low", "result": "incomplete"}
    owned, workers, caps, entry = {}, {}, {}, None
    token = None
    try:
        phase(root,observation,"preflight")
        denied = ("GH", "GH_TOKEN", "GITHUB_TOKEN", "GH_LAOMEDO", "GIT_ASKPASS")
        if any(k in os.environ for k in denied):
            raise ValueError("ambient_credential_environment")
        names = ",".join(tasks.quote(k) for k in denied)
        tasks.powershell("foreach ($s in @('User','Machine')) { foreach ($k in @("+names+
            ")) { if ([Environment]::GetEnvironmentVariables($s).Contains($k)) { throw 'ambient_credentials' } } }")
        connection = HostTokenConnection(connection_id=IDENTITY, generation=1, repository=REPOSITORY,
            token_file=token_file, key="GH_LAOMEDO", forbidden_mount=root)
        token = connection.token(IDENTITY, 1)
        if api(token, "/user").get("login") != "ga84jog" or api(token, "/repos/"+REPOSITORY).get("id") != 1408647759:
            raise ValueError("connection_identity_mismatch")
        trusted = root / "trusted"
        git("clone", "--quiet", "https://github.com/"+REPOSITORY+".git", trusted)
        if git("rev-parse", "HEAD", cwd=trusted) != BASELINE or (trusted / ".github/workflows").exists():
            raise ValueError("baseline_or_workflow_mismatch")
        bundle = root / "baseline.bundle"
        git("bundle", "create", bundle, "refs/heads/main", cwd=trusted)
        for directory in ("host", "runner", "stages"):
            (root / directory).mkdir()
        configurations = {
            "host-services": {"state": str(root/"host"), "repository": REPOSITORY,
                "checkout": str(trusted), "baseline": BASELINE, "agent_mount": str(root/"runner"),
                "runner_state": str(root/"runner"), "private_stage": str(root/"stages"),
                "connection_id": IDENTITY, "connection_generation": 1,
                "token_file": str(token_file.resolve()), "token_key": "GH_LAOMEDO"},
            "bundle-verifier": {"runner_state": str(root/"runner"), "private_root": str(root/"stages"),
                "agent_mount": str(root/"runner"), "baseline_bundle": str(bundle),
                "baseline_sha256": sha256(bundle.read_bytes()).hexdigest()}}
        for name, configuration in configurations.items():
            save(root/(name+".json"), configuration)
        phase(root,observation,"managed_services")
        tasks.register(root, sys.executable, owned)
        mediator, _, before_pids, heartbeat = readiness(root, owned)
        authority = RunGrantAuthority(root/"host/authority.sqlite", connection_authorizer=connection.authorize)
        skill = root/"fixture-skill"
        skill.mkdir()
        (skill/"SKILL.md").write_text("---\nname: crash-probe\n---\nExecute only the exact supplied disposable crash-test command. Never use GitHub or read credentials.\n", encoding="utf-8", newline="\n")
        revision = SkillStore(root/"skill-store").import_skill("crash-probe", skill)
        save(root/"skill-reference.json", {k: revision[k] for k in ("skill_id", "revision_id", "tree_hash")})
        for side in ("b", "a"):
            phase(root,observation,"construct_"+side)
            selected = identities(root, side)
            git("clone", "--quiet", "--no-local", trusted, root/("source-"+side))
            configure_owned_clone(root/("source-"+side), trusted)
            reference = authority.approve(invocation_id=selected["invocation_id"], repository=REPOSITORY,
                branch=selected["branch"], base_branch="main", operations={"actions_read"},
                reviewed_by="owner-selected-real-stage-protocol", connection_id=IDENTITY, connection_generation=1)
            save(root/(side+"-authorization.json"), reference)
            workers[side] = subprocess.Popen([sys.executable,"-m","experiments.exp93.real_stage_worker",
                "--root",str(root),"--side",side], cwd=ROOT, env=_base_git_environment(),
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
            wait_json(root/(side+"-constructed.json"),timeout=30)
        phase(root,observation,"dispatch")
        entry = reserve(LEDGER, root)
        save(root/"observation.json", observation)
        (root/"start-gate").touch(exist_ok=False)
        ready = {s: wait_json(root/(s+"-ready.json"),timeout=30) for s in ("b","a")}
        for side in ("a","b"):
            selected = identities(root, side)
            caps[side] = (root/"host/lease/leases"/selected["token"]/"grant.secret").read_text().strip()
        a = identities(root,"a")
        raw = root/"runner/runs"/a["run_id"]/"raw-events.jsonl"
        deadline = time.monotonic()+45
        boundary = None
        while time.monotonic()<deadline:
            if workers["a"].poll() is not None:
                raise ValueError("agent_ended_before_boundary")
            events = []
            if raw.exists():
                for line in raw.read_text(encoding="utf-8").splitlines():
                    try:
                        events.append(json.loads(line))
                    except ValueError:
                        continue
            boundary = next((e for e in events if e.get("method")=="item/started" and
                (e.get("params",{}).get("item") or {}).get("type")=="commandExecution" and
                "sleep 60" in str((e.get("params",{}).get("item") or {}).get("command"))),None)
            if boundary:
                break
            time.sleep(.05)
        if not boundary:
            raise ValueError("active_command_not_observed")
        phase(root,observation,"runner_loss")
        started = time.monotonic()
        observation["boundary_observed"] = True
        observation["boundary"] = {"method": boundary["method"], "type": "commandExecution",
            "item_id":(boundary.get("params",{}).get("item") or {}).get("id")}
        observation["loss"] = {"command_started": started}
        save(root/"observation.json", observation)
        if inspect_exact(ContainerIdentity(name=a['name'], run_id=a['run_id'], token=a['token'])) != ("owned",ready["a"]["container_id"]):
            raise ValueError("a_ownership_changed")
        observation["boundary_observed"] = True
        native_record = json.loads((root/"runner/runs"/a["run_id"]/"record.json").read_bytes())
        observation["native_identity"] = {k:native_record.get(k) for k in ("run_id","thread_id","turn_id")}
        observation["boundary"] = {"method": boundary["method"], "type": "commandExecution",
            "item_id":(boundary.get("params",{}).get("item") or {}).get("id")}
        original_id = ready["a"]["container_id"]
        _, prekill_running, prekill_checks = exact_container_state(a, original_id)
        if not prekill_running:
            raise ValueError("a_ownership_changed")
        observation["loss"].update({"original_container_id": original_id,
            "prekill_running": prekill_running, "prekill_checks": prekill_checks,
            "kill_started": time.monotonic()})
        save(root/"observation.json", observation)
        killed = kill(workers["a"],ready["a"],root)
        observation["loss"]["kill_completed"] = killed
        save(root/"observation.json", observation)
        revoked = wait_json(root/"host/lease/leases"/a["token"]/"revoked.json",timeout=60)
        observation["loss"]["revoked"] = revoked.get("revoked_at_monotonic")
        save(root/"observation.json", observation)
        if a["grant_id"] not in revoked["revoked_grants"]:
            raise ValueError("wrong_grant_revoked")
        wait_exact_absence(root,a,original_id,killed,observation)
        phase(root,observation,"refusal_and_control")
        before = journal(root)
        status, refusal = mediate(mediator,caps["a"],"pr_create",{
            "head":a["branch"],"base":"main","title":"Denied real-stage test",
            "body":IDENTITY,"marker":IDENTITY})
        denied_at = time.monotonic()
        after = journal(root)
        b = identities(root,"b")
        _, b_owned, b_checks = exact_container_state(b,ready["b"]["container_id"])
        b_status, b_read = mediate(mediator,caps["b"],"actions_read",{"resource":"runs"})
        if not isinstance(b_read,dict):
            raise ValueError("b_result_invalid")
        current = journal(root)
        observation["loss"].update({"denied":denied_at,
            "denial_status":status,"denial_error":refusal.get("error"),
            "attempts_before_denial":len(before),"attempts_after_denial":len(after),
            "a_container_absent":exact_container_state(a,original_id)[0],
            "b_owned_alive":b_owned,"b_running_checks":b_checks,
            "b_read_status":b_status,"b_read_count":len(current)-len(after)})
        save(root/"observation.json",observation)
        _,_,after_pids,new_heartbeat = readiness(root,owned)
        if before_pids != after_pids or new_heartbeat <= heartbeat:
            raise ValueError("managed_services_changed")
        phase(root,observation,"delayed_sentinel")
        while time.monotonic()-started<61:
            if time.monotonic() >= float((root/"deadline").read_text()):
                raise TimeoutError("overall_procedure_deadline")
            time.sleep(.2)
        observation["sentinel_checked_after"] = time.monotonic()-started
        observation["delayed_absence_verified"], _, observation["delayed_absence_checks"] = exact_container_state(a,original_id)
        save(root/"observation.json",observation)
        observation["sentinel_present"] = (root/"runner/runs"/a["run_id"]/"workspace/crash-marker.txt").exists()
        observation["raw_event_sha256"] = sha256(raw.read_bytes()).hexdigest()
        observation["raw_event_count"] = len(raw.read_text().splitlines())
        observation["scanned_files"],observation["secret_hits"] = scan_owned(root,token,caps.values())
        if observation["secret_hits"] != 0:
            raise ValueError("secret_in_private_agent_evidence")
        observation["result"] = "pending_cleanup"
    except Exception as failure:
        observation.update(result="incomplete",failure_class=type(failure).__name__)
        # Only this fixture's finite diagnostic vocabulary is public-safe.
        if str(failure) in {"agent_ended_before_boundary","active_command_not_observed",
                "a_ownership_changed","kill_outcome_unknown","wrong_grant_revoked",
                "service_cleanup_unverified_or_late","independent_container_absence_failed",
                "independent_cleanup_observation_late","service_cleanup_deadline",
                "managed_services_changed","overall_procedure_deadline",
                "docker_inspection_unknown","docker_identity_conflict","service_cleanup_danger_signal"}:
            observation["failure_code"] = str(failure)
    finally:
        observation["cleanup"] = cleanup(root,owned,workers)
        try:
            # B is now stopped; reopening cannot sweep an active control run.
            if observation.get("result") == "pending_cleanup":
                reopened = LocalRunner(root/"runner",root/"skill-store",root/"source-a",
                    check_docker=False,max_model_turns=0,supervise_containers=False,git_workspace=True)
                record = reopened.status(observation["native_identity"]["run_id"])
                observation["restart_status"] = record["status"]
                observation["restart_identity_retained"] = all(record.get(k)==v for k,v in observation["native_identity"].items())
            observation["local_turns"] = json.loads((root/"runner/turn-ledger.json").read_bytes())["attempted_turns"]
            shared = json.loads(LEDGER.read_bytes())
            observation.update(shared_cap=shared["cap"],shared_used=len(shared["attempts"]))
            observation["provider_writes"] = sum(e["operation"] in {"pr_create","pr_update","git_push","issue_create"} for e in journal(root))
            if observation["result"]=="pending_cleanup":
                validate(observation)
                observation["result"]="passed"
        except Exception as failure:
            observation.update(result="incomplete",assessment_error_class=type(failure).__name__)
        if entry:
            try:
                finalize(LEDGER,entry,observation["result"])
            except Exception as failure:
                observation.update(result="incomplete",ledger_finalization_error=type(failure).__name__)
        save(root/"observation.json",observation)
    return observation


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",required=True,type=Path)
    parser.add_argument("--token-file",required=True,type=Path)
    parser.add_argument("--source-sha",required=True)
    parser.add_argument("--review-record",required=True,type=Path)
    parser.add_argument("--allow-one-model-turn",required=True,action="store_true")
    args = parser.parse_args()
    result=run(args.root,args.token_file,args.source_sha,args.review_record)
    print(json.dumps({"identity":IDENTITY,"result":result["result"]}))
    raise SystemExit(0 if result["result"]=="passed" else 1)
