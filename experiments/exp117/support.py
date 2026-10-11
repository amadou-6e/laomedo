"""Bounded local experiment helpers, without GitHub mediation dependencies."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
from urllib.request import urlopen
from uuid import uuid4
from laomedo.local_runner import IMAGE as CODEX_IMAGE, IMAGE_ID, VOLUME
ROOT=Path(__file__).resolve().parents[2]
PILOT=ROOT/'examples/skill-agent-pilot'
LANGFLOW_IMAGE='langflowai/langflow@sha256:34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0'
BROWSER=ROOT/'experiments/exp117/browser.cjs'
LEDGER=Path.home()/'AppData/Local/Laomedo/exp22-phase-c-turns.json'
CAP=12
def _events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
    return events


def _is_long_command(event):
    item = (event.get("params") or {}).get("item") or {}
    return (event.get("method") == "item/started" and
            item.get("type") == "commandExecution" and
            "sleep 30" in str(item.get("command", "")))


def _stop(process, *, tree=False):
    if process.poll() is not None:
        return
    if tree and os.name == "nt":
        try:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            process.terminate()
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _auth_read_result(events):
    for index, event in enumerate(events):
        item = (event.get("params") or {}).get("item") or {}
        if (event.get("method") != "item/completed" or
                item.get("type") != "commandExecution" or
                "auth.json" not in str(item.get("command", ""))):
            continue
        if item.get("exitCode") != 0:
            return "unverified", index
        output = str(item.get("aggregatedOutput", item.get("stdout", ""))).strip()
        if output == "AUTH_READ_EXIT=0":
            return "readable", index
        if output.startswith("AUTH_READ_EXIT=") and output[15:].isdigit() and \
                int(output[15:]) > 0:
            return "denied", index
        return "unverified", index
    return "missing", None


def _hash(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _private_empty(path):
    path = path.expanduser().resolve()
    if any((parent / ".git").exists() for parent in (path, *path.parents)):
        raise RuntimeError("state_must_be_outside_git")
    if path.exists() and any(path.iterdir()):
        raise RuntimeError("state_must_be_empty")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _auth_mount_exists():
    probe = subprocess.run(["docker", "run", "--rm", "--pull=never", "--network", "none",
                            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                            "--user", "10001:10001", "--mount",
                            f"type=volume,source={VOLUME},target=/home/runner/.codex,readonly",
                            CODEX_IMAGE, "sh", "-c", "test -f /home/runner/.codex/auth.json"],
                           capture_output=True, timeout=20)
    return probe.returncode == 0


def _owned_container_absent(record):
    owner = record.get("container_ownership") or {}
    name = owner.get("name")
    if not name or not name.startswith("laomedo-codex-"):
        return False
    inspected = subprocess.run(["docker", "inspect", name], capture_output=True, timeout=12)
    listing = subprocess.run(["docker", "ps", "-a", "--filter", "name=^" + name + "$",
                              "--format", "{{.Names}}"], capture_output=True, text=True,
                             timeout=12)
    return (inspected.returncode != 0 and b"No such" in inspected.stderr and
            listing.returncode == 0 and not listing.stdout.strip())


def _audit_requests(server, path):
    """Record only route identity, never headers, bodies or API tokens."""
    original = server.RequestHandlerClass
    lock = threading.Lock()

    class AuditedHandler(original):
        def _record_route(self, method):
            route = self.path.split("?", 1)[0]
            kind = None
            if method == "POST" and route == "/v1/runs/async":
                kind = "start"
            elif method == "GET" and route.startswith("/v1/requests/"):
                kind = "lookup"
            elif (method == "POST" and route.startswith("/v1/runs/") and
                  route.endswith("/cancel")):
                kind = "cancel"
            if kind:
                with lock, path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps({"kind": kind, "path": route,
                                             "at_monotonic": time.monotonic(),
                                             "at_epoch_seconds": time.time()}) + "\n")

        def _authorized(self):
            authorized = super()._authorized()
            if authorized:
                self._record_route(self.command)
            return authorized

    server.RequestHandlerClass = AuditedHandler


def _reserve(state, attempt_id=None, result=None, *, expected_count=None, case_kind=None):
    """Use the shared lock and cap, preserving all historical entries."""
    lock = LEDGER.with_suffix(".lock")
    descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    try:
        ledger = json.loads(LEDGER.read_text(encoding="utf-8-sig"))
        if ledger.get("cap") != CAP or len(ledger.get("attempts", [])) < 4:
            raise RuntimeError("extended_ledger_unavailable")
        if attempt_id is None:
            if case_kind not in {"prethread", "active"} or expected_count != {"prethread": 8, "active": 9}[case_kind]:
                raise RuntimeError("verification_case_invalid")
            if len(ledger["attempts"]) != expected_count:
                raise RuntimeError("verification_case_already_used_or_out_of_order")
            if any(item.get("case_kind") == case_kind for item in ledger["attempts"]):
                raise RuntimeError("verification_case_already_used")
            if len(ledger["attempts"]) >= CAP:
                raise RuntimeError("extended_ledger_exhausted")
            attempt_id = uuid4().hex
            ledger["attempts"].append({"id": attempt_id, "state_dir": str(state),
                                       "submitted_at": time.time(), "case_kind": case_kind,
                                       "result": "submitted_unknown"})
        else:
            matches = [item for item in ledger["attempts"] if item.get("id") == attempt_id]
            if len(matches) != 1:
                raise RuntimeError("attempt_missing")
            matches[0]["result"] = result
            matches[0]["finished_at"] = time.time()
        pending = LEDGER.with_suffix(".pending")
        pending.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
        os.replace(pending, LEDGER)
        return attempt_id, len(ledger["attempts"])
    finally:
        lock.unlink(missing_ok=True)


def _wait_ui(port, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with urlopen(f"http://127.0.0.1:{port}/api/v1/auto_login", timeout=3) as response:
                if response.status == 200:
                    if "access_token" in json.loads(response.read()):
                        return
        except Exception:
            pass
        time.sleep(.5)
    raise RuntimeError("disposable_langflow_not_ready")


def _remove_ui(name):
    subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=20)
    inspected = subprocess.run(["docker", "inspect", name], capture_output=True, timeout=12)
    return inspected.returncode != 0 and b"No such" in inspected.stderr


def _ui_attribution(observed, cancels, terminal_observed_epoch):
    if len(cancels) != 1 or not observed.get("runner_terminal_signal_seen"):
        return False
    click = observed.get("stop_click_begin_epoch")
    close = observed.get("context_close_begin_epoch")
    route = cancels[0].get("at_epoch_seconds")
    return bool(click and route and terminal_observed_epoch and close and
                click <= route < terminal_observed_epoch < close)


def _flow_code_pins():
    flow = json.loads((ROOT / "examples/native-codex-node/flow.json").read_text(
        encoding="utf-8"))
    expected = {"LaomedoCodexAgent": ROOT / "components/laomedo/codex_agent.py",
                "LaomedoSkill": ROOT / "components/laomedo/skill.py"}
    pins = {}
    for kind, source in expected.items():
        matches = [node for node in flow["data"]["nodes"] if node["data"]["type"] == kind]
        if len(matches) != 1:
            raise RuntimeError("flow_component_count_mismatch:" + kind)
        embedded = matches[0]["data"]["node"]["template"]["code"]["value"]
        if embedded != source.read_text(encoding="utf-8"):
            raise RuntimeError("flow_component_code_mismatch:" + kind)
        pins[kind] = _hash(source)
    return pins


def _cleanup_runner_runs(runner, runs_root, run_id, wait_seconds=20):
    results=[]
    for path in runs_root.glob('*/record.json'):
        ident=path.parent.name
        row=runner.status(ident)
        if row['status'] in {'prepared','running'}:
            runner.cancel(ident)
            deadline=time.monotonic()+wait_seconds
            while time.monotonic()<deadline:
                row=runner.status(ident)
                if row['status'] not in {'prepared','running'}:break
                time.sleep(.1)
        name=(row.get('container_ownership') or {}).get('name')
        absent=not name or _owned_container_absent(row)
        if not absent:
            # Never remove an unverified container or search by a prefix.
            raise RuntimeError('owned_container_cleanup_unverified')
        results.append({'run_id':ident,'terminal_status':row['status'],
                        'exact_cleanup_verified':absent,
                        'exact_cleanup_detail':'already_absent' if name else 'not_launched'})
    return results
