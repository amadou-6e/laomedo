"""Single-use no-provider Windows Task Scheduler diagnostic; see protocol."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


IDENTITY = "exp104-task-s1-20261009"
CHECKOUT = Path(__file__).resolve().parents[2]


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def powershell(command):
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive",
                             "-ExecutionPolicy", "Bypass", "-Command",
                             "$ErrorActionPreference = 'Stop'; " + command],
                            capture_output=True, timeout=35)
    if result.returncode:
        # Do not leak user identity/path from Task Scheduler diagnostics.
        raise RuntimeError("powershell_operation_refused")
    return result.stdout.decode("utf-8-sig").strip()


def processes(configuration):
    command = ("$p = @(Get-CimInstance Win32_Process | Where-Object { "
               "$_.CommandLine -and $_.CommandLine.Contains(" + quote(configuration) +
               ") -and $_.CommandLine.Contains('laomedo.managed_service') }); "
               "ConvertTo-Json -Compress -InputObject @($p.ProcessId)")
    return json.loads(powershell(command))


def run(private: Path):
    if os.name != "nt":
        raise ValueError("windows_required")
    source = subprocess.run(["git", "rev-parse", "HEAD"], cwd=CHECKOUT,
                            check=True, capture_output=True).stdout.decode().strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=CHECKOUT,
                           check=True, capture_output=True).stdout
    if dirty.strip():
        raise ValueError("probe_checkout_not_clean")
    private.mkdir(parents=True, exist_ok=True)
    claim = private / (IDENTITY + ".claim")
    with claim.open("x", encoding="utf-8") as file:
        file.write(IDENTITY + "\n")
    root = Path(tempfile.mkdtemp(prefix=IDENTITY + "-"))
    observation = {"identity": IDENTITY, "model_turns": 0,
                   "provider_operations": 0, "result": "failed",
                   "source_sha": source, "tasks": {}, "cleanup": {}}
    for name in ("state", "runner", "private", "agent", "checkout"):
        (root / name).mkdir()
    token = root / "synthetic.env"
    token.write_text("SYNTHETIC=not-a-github-credential\n", encoding="utf-8")
    baseline = root / "baseline.bundle"
    baseline.write_bytes(b"no-stage-attempts-in-this-probe")
    values = {
        "host-services": {"state": str(root / "state"),
                          "repository": "example/disposable",
                          "checkout": str(root / "checkout"), "baseline": "a" * 40,
                          "agent_mount": str(root / "agent"),
                          "connection_id": IDENTITY, "connection_generation": 1,
                          "token_file": str(token), "token_key": "SYNTHETIC"},
        "bundle-verifier": {"runner_state": str(root / "runner"),
                            "private_root": str(root / "private"),
                            "agent_mount": str(root / "agent"),
                            "baseline_bundle": str(baseline),
                            "baseline_sha256": sha256(baseline.read_bytes()).hexdigest()},
    }
    owned = {}
    runner = None
    try:
        for service, configuration in values.items():
            path = root / (service + ".json")
            path.write_text(json.dumps(configuration), encoding="utf-8")
            installer = CHECKOUT / "scripts" / "Install-LaomedoUserTask.ps1"
            task = powershell("& " + quote(installer) + " -Service " + quote(service) +
                              " -Python " + quote(sys.executable) + " -Checkout " +
                              quote(CHECKOUT) + " -Configuration " + quote(path))
            owned[service] = (task, path)
            powershell("Start-ScheduledTask -TaskPath '\\' -TaskName " + quote(task))
        before = {}
        deadline = time.monotonic() + 20
        heartbeat = root / "state" / "lease" / "service.alive"
        while time.monotonic() < deadline:
            before = {service: processes(path) for service, (_, path) in owned.items()}
            if all(ids for ids in before.values()) and heartbeat.is_file():
                break
            time.sleep(.2)
        if not all(before.values()) or not heartbeat.is_file():
            raise RuntimeError("task_readiness_failed")
        mediator = json.loads((root / "state" / "mediator" / "mediator.json").read_text())
        observation["host_module_root_matches"] = (
            Path(mediator["module_root"]).resolve() == CHECKOUT / "laomedo")
        if not observation["host_module_root_matches"]:
            raise RuntimeError("host_source_mismatch")
        old_heartbeat = heartbeat.read_text()
        # Exact stand-in runner has no services as children. Killing its tree
        # must leave the two Scheduler-owned service processes unchanged.
        runner = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["taskkill", "/PID", str(runner.pid), "/T", "/F"],
                       check=True, capture_output=True, timeout=10)
        runner.wait(timeout=5)
        time.sleep(5)
        after = {service: processes(path) for service, (_, path) in owned.items()}
        for service, (task, _) in owned.items():
            settings = json.loads(powershell(
                "$t = Get-ScheduledTask -TaskPath '\\' -TaskName " + quote(task) +
                "; @{ limited = ($t.Principal.RunLevel -eq 'Limited'); "
                "interactive = ($t.Principal.LogonType -eq 'Interactive'); "
                "ignore_new = ($t.Settings.MultipleInstances -eq 'IgnoreNew') } | ConvertTo-Json -Compress"))
            observation["tasks"][service] = dict(settings, before=before[service],
                                                  after=after[service])
        observation["heartbeat_advanced"] = heartbeat.read_text() != old_heartbeat
        observation["runner_stopped"] = runner.returncode is not None
        journal = root / "state" / "mediator" / "provider-attempts.jsonl"
        if journal.exists() and journal.read_text().strip():
            raise RuntimeError("unexpected_provider_attempt")
        if (before != after or not observation["heartbeat_advanced"] or
                not all(all(v for k, v in item.items() if k not in {"before", "after"})
                        for item in observation["tasks"].values())):
            raise RuntimeError("task_survival_failed")
        observation["result"] = "passed"
    except Exception as failure:
        observation["failure_class"] = type(failure).__name__
    finally:
        if runner is not None and runner.poll() is None:
            runner.kill()
            runner.wait(timeout=5)
        for service, (task, path) in owned.items():
            try:
                powershell("$t = Get-ScheduledTask -TaskPath '\\' -TaskName " + quote(task) +
                           "; if ($t.Description -ne 'Laomedo managed per-user host process v1' "
                           "-or -not $t.Actions.Arguments.Contains(" + quote(path) +
                           ")) { throw 'task_ownership_changed' }; "
                           "Stop-ScheduledTask -TaskPath '\\' -TaskName " + quote(task) +
                           "; Unregister-ScheduledTask -TaskPath '\\' -TaskName " +
                           quote(task) + " -Confirm:$false; "
                           "if (Get-ScheduledTask -TaskPath '\\' -TaskName " + quote(task) +
                           " -ErrorAction SilentlyContinue) { throw 'task_remains' }")
                time.sleep(1)
                observation["cleanup"][service] = not processes(path)
            except Exception:
                observation["cleanup"][service] = False
        if any(value is not True for value in observation["cleanup"].values()):
            observation["result"] = "cleanup_unverified"
        output = private / (IDENTITY + ".json")
        with output.open("x", encoding="utf-8", newline="\n") as file:
            json.dump(observation, file, sort_keys=True, indent=2)
            file.write("\n")
    return observation


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-state", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.private_state), sort_keys=True))
