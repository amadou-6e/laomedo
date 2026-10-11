"""One-shot no-model Langflow feedback experiment, after independent review."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time
from urllib import error, parse, request

from experiments.exp123.runtime import HEADS, signed

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
IMAGE = "langflowai/langflow@sha256:34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0"
NAME = "laomedo-exp123-s1-20261009"
BASE = "http://127.0.0.1:17873"
CASES = ("success", "early", "pending", "repair", "cap", "stop", "crash")
SOURCES = ("agent.py", "gate.py", "router.py", "terminal.py", "runtime.py", "probe.py", "test_probe.py")


def docker(*args, check=True):
    done = subprocess.run(["docker", *args], capture_output=True, text=True,
                          timeout=45, check=False)
    if check and done.returncode:
        raise RuntimeError("docker_" + args[0] + "_failed")
    return done.stdout.strip()


def api(method, path, body=None):
    encoded = None if body is None else json.dumps(body).encode()
    req = request.Request(BASE + path, data=encoded, method=method,
                          headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=3) as response:
        return json.load(response)


def health():
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            if api("GET", "/health").get("ready"):
                return
        except (OSError, ValueError):
            pass
        time.sleep(.2)
    raise TimeoutError("worker_health")


def snapshot(run):
    return api("GET", "/case?" + parse.urlencode({"run_id": run}))


def wait(run, predicate):
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        current = snapshot(run)
        if predicate(current):
            return current
        if current["state"] != "running":
            raise RuntimeError("case_ended_before_expected_event:" + json.dumps(current))
        time.sleep(.1)
    raise TimeoutError("case_controller_deadline")


def waiting(run, index):
    return wait(run, lambda case: any(row["kind"] == "gate_waiting" and
        row.get("gate_id") == run + ":gate-" + str(index) for row in case["events"]))


def fixture(run, index, status, delivery, **changes):
    return signed({"run_id": run, "gate_id": run + ":gate-" + str(index),
        "repository": "fixture/repo", "pr_number": 1, "head_sha": HEADS[index - 1],
        "source_check_id": run + ":check-" + str(index),
        "source_delivery_id": run + ":delivery-" + delivery, "status": status, **changes})


def assess(name, result):
    rows = result["events"]
    graphs = [row for row in rows if row["kind"] == "graph_started"]
    agents = [row for row in rows if row["kind"] == "agent_invoked"]
    decisions = [row for row in rows if row["kind"] == "gate_decided"]
    terminals = [row for row in rows if row["kind"] == "terminal_result"]
    expected_agents = 2 if name in {"repair", "cap"} else 1
    if len(graphs) != 1 or len(agents) != expected_agents:
        raise AssertionError("graph_or_invocation_count")
    if len({row["invocation_id"] for row in agents}) != len(agents):
        raise AssertionError("invocation_identity_reused")
    actual = {row["graph_id"] for row in rows if "node_id" in row}
    if actual != {graphs[0]["graph_id"]}:
        raise AssertionError("graph_identity_join")
    if [row["head_sha"] for row in agents] != list(HEADS[:expected_agents]):
        raise AssertionError("agent_head_sequence")
    for row in decisions:
        index = int(row["gate_id"].rsplit("-", 1)[1])
        if row["head_sha"] != HEADS[index - 1] or row["source_check_id"] != result["run_id"] + ":check-" + str(index):
            raise AssertionError("gate_correlation")
    expected_state = "interrupted" if name == "stop" else "crashed" if name == "crash" else "completed"
    if result["state"] != expected_state:
        raise AssertionError("terminal_state")
    if name in {"stop", "crash"}:
        if decisions or terminals:
            raise AssertionError("dispatch_after_stop_or_crash")
        if name == "stop" and not any(row["kind"] == "gate_cancelled" for row in rows):
            raise AssertionError("stop_not_observed_by_gate")
    else:
        expected = ["failed", "failed" if name == "cap" else "passed"] if expected_agents == 2 else ["passed"]
        if [row["status"] for row in decisions] != expected or len(terminals) != 1:
            raise AssertionError("route_or_terminal_count")
        if terminals[0]["status"] != expected[-1]:
            raise AssertionError("terminal_result_invented")
    if name == "early":
        final = next(row for row in rows if row["kind"] == "delivery" and row["classification"] == "accepted")
        if final["sequence"] >= graphs[0]["sequence"]:
            raise AssertionError("early_fixture_not_early")
    if name == "repair":
        observed = {row["classification"] for row in rows if row["kind"] == "delivery"}
        if not {"duplicate", "conflict", "refused"} <= observed:
            raise AssertionError("missing_correlation_controls")
    return {"graph_count": len(graphs), "invocation_count": len(agents),
            "gate_decisions": [row["status"] for row in decisions], "terminal_state": result["state"]}


def run_case(name, captures):
    run = "exp123-S1-" + name
    def send(path, body):
        started = time.monotonic()
        response = api("POST", path, body)
        captures.append({"path": path, "request": body, "response": response,
                         "started_monotonic": started, "finished_monotonic": time.monotonic()})
        return response
    send("/reserve", {"run_id": run, "case_name": name})
    if name == "early":
        send("/event", fixture(run, 1, "passed", "early"))
    send("/start", {"run_id": run})
    waiting(run, 1)
    time.sleep(.2)
    if name == "stop":
        send("/stop", {"run_id": run})
        wait(run, lambda current: current["state"] == "interrupted")
        send("/event", fixture(run, 1, "failed", "after-stop"))
    elif name == "crash":
        inspected = json.loads(docker("inspect", NAME))[0]
        if inspected["Config"]["Labels"].get("laomedo.exp123") != "S1":
            raise RuntimeError("container_identity_changed")
        docker("kill", "--signal", "KILL", inspected["Id"])
        docker("start", inspected["Id"])
        health()
        send("/event", fixture(run, 1, "failed", "after-crash"))
    elif name in {"repair", "cap"}:
        failed = fixture(run, 1, "failed", "failed-h1")
        send("/event", failed)
        waiting(run, 2)
        time.sleep(.2)
        if name == "repair":
            send("/event", failed)
            send("/event", fixture(run, 1, "passed", "conflict-h1"))
            send("/event", fixture(run, 2, "passed", "stale-h1", head_sha=HEADS[0]))
        send("/event", fixture(run, 2, "failed" if name == "cap" else "passed", "final-h2"))
    elif name == "pending":
        invalid = fixture(run, 1, "passed", "invalid")
        invalid["signature"] = "0" * 64
        send("/event", invalid)
        send("/event", fixture(run, 1, "unknown", "unknown"))
        time.sleep(.2)
        send("/event", fixture(run, 1, "pending", "pending"))
        time.sleep(.2)
        if any(row["kind"] == "gate_decided" for row in snapshot(run)["events"]):
            raise AssertionError("nonfinal_dispatched")
        send("/event", fixture(run, 1, "passed", "final"))
    elif name == "success":
        send("/event", fixture(run, 1, "passed", "final"))
    final = wait(run, lambda current: current["state"] != "running")
    time.sleep(1)
    final = snapshot(run)
    return final, assess(name, final)


def validate_capture(cases, journal, flows):
    """Reject summaries that cannot be reconstructed from captured bytes."""
    rows = [json.loads(line) for line in journal.splitlines()]
    if [row["sequence"] for row in rows] != list(range(1, len(rows) + 1)):
        raise AssertionError("journal_sequence")
    for name, case in cases.items():
        run = case["raw"]["run_id"]
        recorded = [row for row in rows if row["run_id"] == run]
        if recorded != case["raw"]["events"]:
            raise AssertionError("journal_snapshot_mismatch")
        started = [row for row in recorded if row["kind"] == "graph_started"]
        if len(started) != 1 or hashlib.sha256(flows[name]).hexdigest() != started[0]["graph_sha256"]:
            raise AssertionError("flow_snapshot_mismatch")
        if assess(name, case["raw"]) != case["assessment"]:
            raise AssertionError("assessment_mismatch")


def owned_container():
    entries = json.loads(docker("inspect", NAME))
    item = entries[0]
    if (len(entries) != 1 or item["Name"] != "/" + NAME or
            (item["Config"].get("Labels") or {}).get("laomedo.exp123") != "S1"):
        raise RuntimeError("container_ownership_unverified")
    return item["Id"]


def cleanup_owned():
    """Never remove a name-matching resource without checking its label."""
    if docker("ps", "-a", "--filter", "name=^" + NAME + "$", "--format", "{{.Names}}"):
        docker("rm", "--force", owned_container())
    volumes = json.loads(docker("volume", "inspect", NAME))
    if (len(volumes) != 1 or volumes[0]["Name"] != NAME or
            (volumes[0].get("Labels") or {}).get("laomedo.exp123") != "S1"):
        raise RuntimeError("volume_ownership_unverified")
    docker("volume", "rm", NAME)
    if (docker("ps", "-a", "--filter", "name=^" + NAME + "$", "--format", "{{.Names}}") or
            docker("volume", "ls", "--filter", "name=^" + NAME + "$", "--format", "{{.Name}}")):
        raise RuntimeError("cleanup_not_verified")


def main(source_commit):
    if not re_full_sha(source_commit):
        raise ValueError("source_commit_invalid")
    source_hashes = {}
    for filename in SOURCES:
        relative = "experiments/exp123/" + filename
        frozen = subprocess.run(["git", "show", source_commit + ":" + relative], cwd=ROOT,
                                capture_output=True, check=True).stdout
        current = (HERE / filename).read_bytes()
        if current.replace(b"\r\n", b"\n") != frozen:
            raise RuntimeError("candidate_source_changed:" + filename)
        source_hashes[filename] = hashlib.sha256(frozen).hexdigest()
    destination = HERE / "observation-s1.json"
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump({"identity": "S1", "state": "reserved"}, stream)
        stream.write("\n")
    report = {"identity": "S1", "source_commit": source_commit,
              "source_hashes": source_hashes, "image": IMAGE,
              "model_turns": 0, "provider_writes": 0, "cases": {}, "requests": []}
    owned = False
    try:
        if docker("ps", "-a", "--filter", "name=^" + NAME + "$", "--format", "{{.Names}}") or docker(
            "volume", "ls", "--filter", "name=^" + NAME + "$", "--format", "{{.Name}}"):
            raise RuntimeError("disposable_identity_in_use")
        docker("volume", "create", "--label", "laomedo.exp123=S1", NAME)
        owned = True
        docker("run", "--rm", "--network", "none", "--user", "0", "-v", NAME + ":/state",
               "--entrypoint", "chown", IMAGE, "1000:0", "/state")
        docker("run", "-d", "--name", NAME, "--label", "laomedo.exp123=S1",
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
               "--memory", "1g", "--pids-limit", "128", "-p", "127.0.0.1:17873:18743",
               "-e", "PYTHONPATH=/candidate", "-v", str(HERE) + ":/candidate/experiments/exp123:ro",
               "-v", NAME + ":/state", "--entrypoint", "python", IMAGE,
               "-m", "experiments.exp123.runtime")
        health()
        for name in CASES:
            result, assessment = run_case(name, report["requests"])
            report["cases"][name] = {"raw": result, "assessment": assessment}
        report["state"] = "passed"
    except Exception as failure:
        report["state"] = "failed"
        report["error_class"] = type(failure).__name__
        report["error"] = str(failure)[:1000]
    finally:
        report["evidence_hashes"] = {}
        try:
            evidence = HERE / "evidence" / "S1"
            evidence.mkdir(parents=True, exist_ok=False)
            def save(filename, data):
                (evidence / filename).write_bytes(data)
                report["evidence_hashes"][filename] = hashlib.sha256(data).hexdigest()
            if owned:
                container_id = owned_container()
                journal = subprocess.run(["docker", "exec", container_id, "cat", "/state/journal.jsonl"],
                                         capture_output=True, check=True, timeout=15).stdout
                save("journal.jsonl", journal)
                flows = {}
                for name, case in report["cases"].items():
                    run = case["raw"]["run_id"]
                    raw = snapshot(run)
                    if raw != case["raw"]:
                        raise AssertionError("case_changed_during_capture")
                    save(name + ".json", (json.dumps(raw, indent=2, sort_keys=True) + "\n").encode())
                    flows[name] = subprocess.run(["docker", "exec", container_id, "cat",
                        "/state/" + run + ".flow.json"], capture_output=True, check=True, timeout=15).stdout
                    save(name + ".flow.json", flows[name])
                validate_capture(report["cases"], journal, flows)
                report["capture_verified"] = True
        except Exception as capture_failure:
            report["state"] = "failed"
            report["capture_error"] = type(capture_failure).__name__ + ":" + str(capture_failure)[:600]
        finally:
            if owned:
                try:
                    cleanup_owned()
                    report["cleanup_verified"] = True
                except Exception as cleanup_failure:
                    report["state"] = "failed"
                    report["cleanup_verified"] = False
                    report["cleanup_error"] = type(cleanup_failure).__name__ + ":" + str(cleanup_failure)[:600]
        destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8", newline="\n")
    print(json.dumps({"identity": "S1", "state": report["state"],
                      "cases_recorded": list(report["cases"]), "error_class": report.get("error_class")}))
    return report


def re_full_sha(value):
    return len(value) == 40 and all(c in "0123456789abcdef" for c in value)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", required=True, choices=["S1"])
    parser.add_argument("--source-commit", required=True)
    parsed = parser.parse_args()
    main(parsed.source_commit)
