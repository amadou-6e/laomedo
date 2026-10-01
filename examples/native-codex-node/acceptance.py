"""Bounded local #21 acceptance, with private responses and an existing runner ledger.

Run each phase explicitly. This never starts a server, copies authentication,
or resets a ledger. Authorize model turns separately before first/resume/fresh/cancel.
"""

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from urllib import error, request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from laomedo.local_runner import _private

STATE = _private(Path(os.environ["LOCALAPPDATA"]) / "Laomedo/native-node-21")
BASE = "http://127.0.0.1:7862"
RUNNER = "http://127.0.0.1:8766"
NODE = "LaomedoCodexAgent-native"
MARKER = "NATIVE-NODE-21-MARKER"


def save(name, value):
    (STATE / (name + ".json")).write_text(json.dumps(value, indent=2))


def call(url, payload=None, *, token=None, api_key=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if api_key:
        headers["x-api-key"] = api_key
    req = request.Request(url, headers=headers,
        data=None if payload is None else json.dumps(payload).encode())
    try:
        with request.urlopen(req, timeout=240) as response:
            content = response.read()
            if response.headers.get("Content-Encoding") == "gzip":
                content = gzip.decompress(content)
            return {"http": response.status, "body": json.loads(content)}
    except error.HTTPError as exc:
        return {"http": exc.code, "body": json.load(exc)}


def login():
    response = call(BASE + "/api/v1/auto_login")
    assert response["http"] == 200, "local_login_failed"
    return response["body"]["access_token"]  # memory only


def records():
    return {p.parent.name: json.loads(p.read_text())
            for p in (STATE / "runs").glob("*/record.json")}


def events(run_id):
    return [json.loads(line) for line in
            (STATE / "runs" / run_id / "raw-events.jsonl").read_text().splitlines() if line]


def run_flow(task, *, operation="fresh", prior=None, extra=None):
    token = login()
    key = call(BASE + "/api/v1/api_key/", {"name": "native-node-21-test"}, token=token)
    assert key["http"] in {200, 201}, "local_api_key_failed"
    flow_id = json.loads((STATE / "flow-id.json").read_text())["flow_id"]
    tweaks = {"operation": operation, "runner_url": "http://host.docker.internal:8766"}
    if prior:
        tweaks["run_reference_json"] = json.dumps(prior)
    tweaks.update(extra or {})
    return call(BASE + "/api/v1/run/" + flow_id, {
        "input_value": task, "input_type": "chat", "output_type": "chat",
        "tweaks": {NODE: tweaks}}, token=token, api_key=key["body"]["api_key"])


def reference(record):
    return {"run_id": record["run_id"], "thread_id": record["thread_id"],
            "status": record["status"], "post_run_hash": record["post_run_hash"],
            "model": record["requested_model"], "effort": record["requested_effort"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["prepare", "preflight", "first", "resume", "fresh", "cancel", "inspect"])
    parser.add_argument("--approved-model-turn", action="store_true")
    args = parser.parse_args()
    if args.phase in {"first", "resume", "fresh", "cancel"} and not args.approved_model_turn:
        parser.error("requires separate bounded authorization and --approved-model-turn")
    STATE.mkdir(parents=True, exist_ok=True)
    if args.phase == "prepare":
        token = login()
        catalog = call(BASE + "/api/v1/all", token=token)
        assert catalog["http"] == 200 and "LaomedoCodexAgent" in json.dumps(catalog["body"])
        save("catalog", {"http": catalog["http"], "native_node_present": True})
        flow = json.loads(Path(__file__).with_name("flow.json").read_text())
        flow.pop("id", None)
        imported = call(BASE + "/api/v1/flows/", flow, token=token)
        assert imported["http"] in {200, 201}, "flow_import_failed"
        flow_id = imported["body"]["id"]
        exported = call(BASE + "/api/v1/flows/" + flow_id, token=token)
        assert exported["http"] == 200
        assert any(n["data"]["type"] == "LaomedoCodexAgent" for n in exported["body"]["data"]["nodes"])
        second = exported["body"]
        second.pop("id", None)
        second["name"] += " reimported"
        reimported = call(BASE + "/api/v1/flows/", second, token=token)
        assert reimported["http"] in {200, 201}
        save("flow-id", {"flow_id": reimported["body"]["id"], "original_flow_id": flow_id})
        save("pins", {"implementation": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip(),
             "skill_sha256": hashlib.sha256((ROOT / "examples/skill-agent-pilot/skill/SKILL.md").read_bytes()).hexdigest(),
             "flow_sha256": hashlib.sha256(Path(__file__).with_name("flow.json").read_bytes()).hexdigest(),
             "permission_sha256": hashlib.sha256((ROOT / "experiments/feasibility/122/container/runner-config.toml").read_bytes()).hexdigest(),
             "model": "gpt-6-luna", "effort": "low", "approved_cap": 4})
        print("installed_catalog_and_import_export_reimport_passed; submitted_turns=0")
    elif args.phase == "preflight":
        ledger = STATE / "turn-ledger.json"
        before = ledger.read_bytes() if ledger.exists() else None
        bad_skill = run_flow("Must fail before dispatch", extra={"revision_id": "latest"})
        bad_resume = run_flow("Must not start fresh", operation="resume", prior={
            "run_id": "aeb54b12-3ca7-43a7-97b3-762dadc94721"})
        assert bad_skill["http"] != 200 and bad_resume["http"] != 200
        assert (ledger.read_bytes() if ledger.exists() else None) == before
        assert not records(), "preflight_created_runner_records"
        save("preflight", {"mutable_skill_http": bad_skill["http"],
                           "incomplete_resume_http": bad_resume["http"], "ledger_unchanged": True})
        print("preflight_failures_rejected_without_dispatch")
    elif args.phase in {"first", "fresh"}:
        before = set(records())
        task = ("Read the laomedo-pilot SKILL.md and fixture.txt with shell tools. "
                "Count amber occurrences. Write native-marker.txt containing " + MARKER +
                " and read it back. Report the marker and count. Do not change any other files."
                if args.phase == "first" else
                "Read the laomedo-pilot SKILL.md and fixture.txt with shell tools. "
                "Test whether native-marker.txt exists using a shell command. Report "
                "FRESH-MARKER-ABSENT if absent; do not create any files.")
        response = run_flow(task)
        save(args.phase + "-response", response)
        assert response["http"] == 200, "flow_run_failed; inspect private response"
        after = records()
        added = set(after) - before
        assert len(added) == 1, "unexpected_dispatch_count"
        record = after[added.pop()]
        assert record["status"] == "completed"
        command_results = [e for e in events(record["run_id"]) if e.get("method") == "item/completed"
                           and e.get("params", {}).get("item", {}).get("type") == "commandExecution"]
        assert command_results, "no_observed_command_result"
        workspace = STATE / "runs" / record["run_id"] / "workspace"
        if args.phase == "first":
            assert (workspace / "native-marker.txt").read_text().strip() == MARKER
            save("first-reference", reference(record))
        else:
            assert not (workspace / "native-marker.txt").exists()
            assert "FRESH-MARKER-ABSENT" in record["answer"]
        save(args.phase + "-summary", {**reference(record), "observed_command_results": len(command_results)})
        print(args.phase + "_passed; run_id=" + record["run_id"])
    elif args.phase == "resume":
        prior = json.loads((STATE / "first-reference.json").read_text())
        response = run_flow("Read native-marker.txt and fixture.txt with shell tools. Report the "
                            "exact marker and amber count. Do not modify files.", operation="resume", prior=prior)
        save("resume-response", response)
        assert response["http"] == 200, "resume_failed"
        record = records()[prior["run_id"]]
        assert record["status"] == "completed" and record["thread_id"] == prior["thread_id"]
        assert record["post_run_hash"] == prior["post_run_hash"] and MARKER in record["answer"]
        assert len(record["turns"]) == 2
        save("resume-summary", {**reference(record), "same_thread": True, "same_snapshot": True})
        print("resume_through_imported_node_passed")
    elif args.phase == "cancel":
        before = set(records())
        responses = []
        failures = []
        def invoke():
            try:
                responses.append(run_flow("Read fixture.txt, print INTERRUPT-READY, sleep 60 seconds, "
                                          "then print INTERRUPT-END using one shell command. Do not modify files."))
            except Exception as exc:
                failures.append(type(exc).__name__)
        worker = threading.Thread(target=invoke)
        worker.start()
        deadline = time.monotonic() + 120
        run_id = None
        while worker.is_alive() and time.monotonic() < deadline:
            for candidate in set(records()) - before:
                try:
                    observed = events(candidate)
                except FileNotFoundError:
                    continue
                if any(e.get("method") == "item/started" and
                       e.get("params", {}).get("item", {}).get("type") == "commandExecution" and
                       "sleep" in e["params"]["item"].get("command", "") for e in observed):
                    run_id = candidate
                    break
            if run_id:
                break
            time.sleep(0.2)
        assert run_id, "no_interruptible_command_observed"
        # This tests the node's explicit cancel operation, not UI Stop propagation.
        cancel = run_flow("", operation="cancel", prior={"run_id": run_id})
        worker.join(120)
        record = records()[run_id]
        assert not worker.is_alive() and record["status"] == "cancelled"
        assert cancel["http"] == 200 and responses and responses[0]["http"] != 200
        save("cancel-response", responses[0])
        save("cancel-summary", {"run_id": run_id, "status": record["status"],
                               "partial_events": len(events(run_id)), "cancel_node_http": cancel["http"]})
        print("explicit_cancel_through_node_passed")
    else:
        ledger = json.loads((STATE / "turn-ledger.json").read_text())
        print(json.dumps({"ledger": ledger, "runs": [{k: r.get(k) for k in
              ["run_id", "thread_id", "status", "attempt_number"]} for r in records().values()]}))


if __name__ == "__main__":
    main()
