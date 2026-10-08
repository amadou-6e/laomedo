"""No-model Docker check of Codex command/exec through the file bridge."""

import json
from pathlib import Path
import tempfile
import threading
from uuid import uuid4

from laomedo.file_mediation_bridge import FileMediationBridge
from laomedo.github_mediation import MediationStore
from laomedo.local_runner import AppServer, _docker_prefix


def main():
    with tempfile.TemporaryDirectory(prefix="laomedo-phase-c-file-") as directory:
        root = Path(directory)
        run_id, lease_token = str(uuid4()), uuid4().hex
        run = root / "runs" / run_id
        for name in ("workspace", "canonical", "store", "bridge-spool",
                     "bridge-responses", "evidence"):
            (run / name).mkdir(parents=True)
        lease = root / "lease" / "leases" / lease_token
        lease.mkdir(parents=True)
        store = MediationStore(root / "mediator.sqlite")
        grant_id, secret = store.issue(
            run_id=run_id, invocation_id="phase-c-preflight",
            repository="example/disposable", branch="phase-c-a",
            operations={"pr_update"}, target_prs={7: "main"},
            ttl_seconds=60, lease_token=lease_token,
            lease_scope="preflight", service_instance="preflight")
        (lease / "lease.json").write_text(json.dumps({"token": lease_token,
                                                       "run_id": run_id}), encoding="utf-8")
        (lease / "accepted.json").write_text(json.dumps({"token": lease_token,
                                                           "grant_id": grant_id}), encoding="utf-8")
        (lease / "grant.secret").write_text(secret, encoding="utf-8")
        (run / "record.json").write_text(json.dumps({
            "run_id": run_id,
            "container_ownership": {"launch_token": lease_token,
                                    "grant_id": grant_id}}), encoding="utf-8")
        calls = []

        def transport(repository, operation, payload, **_binding):
            calls.append((repository, operation, payload.get("number")))
            return {"synthetic": True}

        bridge = FileMediationBridge(root / "runs", root / "lease", store,
                                     transport, root / "bridge-journal.jsonl")
        stop = threading.Event()
        worker = threading.Thread(target=bridge.serve,
                                  args=(stop, root / "bridge-status.json"), daemon=True)
        worker.start()
        server = None
        try:
            command = ["docker", *_docker_prefix(
                run / "workspace", run / "canonical", run / "store",
                file_responses=run / "bridge-responses")]
            server = AppServer(command, run / "evidence")
            result = server.request("initialize", {"clientInfo": {
                "name": "laomedo_phase_c_file", "title": "Phase C File Check",
                "version": "0.1.0"}})
            if "result" not in result:
                raise RuntimeError("initialize_rejected")
            server.notify("initialized", {})
            auth_check = server.request("command/exec", {
                "command": ["sh", "-c", "cat /home/runner/.codex/auth.json >/dev/null 2>&1; printf 'AUTH_READ_EXIT=%s\\n' \"$?\""],
                "cwd": "/draft", "timeoutMs": 10000}, timeout=20).get("result") or {}
            auth_output = str(auth_check.get("stdout", ""))
            if (auth_check.get("exitCode") != 0 or
                    "AUTH_READ_EXIT=1" not in auth_output):
                raise RuntimeError("auth_read_denial_unverified")
            script = """
const fs=require('node:fs');
const body={repository:'example/disposable',operation:'pr_update',
payload:{number:7,head:'phase-c-a',base:'main',marker:'preflight'},
effect_id:'phase-c-file-preflight'};
fs.writeFileSync('/draft/preflight-request.json', JSON.stringify(body));
console.log('REQUEST_READY');
"""
            wrote = server.request("command/exec", {
                "command": ["node", "-e", script], "cwd": "/draft",
                "timeoutMs": 10000}, timeout=20).get("result") or {}
            if wrote.get("exitCode") != 0 or not (
                    run / "workspace" / "preflight-request.json").exists():
                raise RuntimeError("agent_request_write_failed")
            response = server.request("command/exec", {
                "command": ["node", "/run/laomedo/mediate.mjs",
                            "--request-file", "/draft/preflight-request.json"],
                "cwd": "/draft",
                "timeoutMs": 25000}, timeout=35)
            result = response.get("result") or {}
            output = str(result.get("stdout", ""))
            journal_path = root / "bridge-journal.jsonl"
            journal = ([json.loads(line) for line in journal_path.read_text(
                encoding="utf-8").splitlines()] if journal_path.exists() else [])
            checked = {"exit_code": result.get("exitCode"),
                       "confirmed": '"state":"confirmed"' in output,
                       "auth_read_denied": True,
                       "fake_calls": len(calls),
                       "journaled": len(journal) == 1 and
                           journal[0].get("state") == "confirmed",
                       "bearer_mounted": any("target=/run/laomedo/capability" in
                                            entry for entry in command)}
            print(json.dumps(checked, sort_keys=True))
            if (checked["exit_code"] != 0 or not checked["confirmed"] or
                    checked["fake_calls"] != 1 or not checked["journaled"] or
                    checked["bearer_mounted"]):
                raise RuntimeError("file_bridge_preflight_failed")
        finally:
            if server is not None:
                server.close()
            stop.set()
            worker.join(timeout=3)


if __name__ == "__main__":
    main()
