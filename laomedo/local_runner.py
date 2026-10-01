"""Single-user local Codex runner backed by the tested Docker profile."""

from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import shutil
import stat
import subprocess
import threading
import time
from uuid import UUID, uuid4

from .skill_store import SkillStore, SkillStoreError, inventory, tree_hash
from .artifacts import ArtifactError, import_selected, relative_path, selections


IMAGE = "laomedo-codex-boundary:0.159.2"
IMAGE_ID = "sha256:7b79ce12be47d6c8262dd4043895112d204416bda5cd891d124775df55587239"
CLI_VERSION = "codex-cli 0.159.2"
VOLUME = "laomedo-122-docker-auth"
CONFIG = Path(__file__).resolve().parents[1] / "experiments/feasibility/122/container/runner-config.toml"
CONFIG_SHA256 = "a14cd7e8abb4216b16d29e55809c2c3c9a9c33cc0196fd459fc033aaaa1ea4c4"
MAX_BODY = 64 * 1024


class RunnerError(ValueError):
    pass


def _git_tree(path: Path) -> bool:
    return any((parent / ".git").exists() for parent in (path, *path.parents))


def _private(path: Path) -> Path:
    path = path.expanduser().resolve()
    if _git_tree(path) or path.is_symlink():
        raise RunnerError("private_state_must_be_outside_git")
    return path


def _json(path: Path, value: dict) -> None:
    pending = path.with_name(path.name + ".pending-" + uuid4().hex)
    pending.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(pending, path)


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RunnerError("invalid_record")
    return value


def _hash_tree(path: Path) -> str:
    """Hash regular files and directories, including empty directories."""
    if not path.is_dir() or path.is_symlink():
        raise RunnerError("invalid_workspace")
    files = {}
    directories = []
    for parent, dirs, names in os.walk(path, followlinks=False):
        for name in dirs + names:
            item = Path(parent) / name
            if (item.is_symlink() or
                    getattr(item.lstat(), "st_file_attributes", 0) &
                    getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0) or
                    not (item.is_dir() or item.is_file())):
                raise RunnerError("unsafe_workspace_entry")
            if item.is_file():
                if item.stat().st_nlink != 1:
                    raise RunnerError("unsafe_workspace_entry")
                files[item.relative_to(path).as_posix()] = item.read_bytes()
            else:
                directories.append(item.relative_to(path).as_posix())
    digest = hashlib.sha256()
    for relative in sorted(directories):
        encoded = relative.encode("utf-8")
        digest.update(b"D")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    for relative, data in sorted(files.items()):
        encoded = relative.encode("utf-8")
        digest.update(b"F")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return "sha256:" + digest.hexdigest()


def _copy_tree(source: Path, target: Path) -> str:
    expected = _hash_tree(source)
    shutil.copytree(source, target)
    if _hash_tree(target) != expected:
        raise RunnerError("workspace_copy_mismatch")
    return expected


def _id(value: str) -> str:
    if str(UUID(value)) != value:
        raise RunnerError("invalid_run_id")
    return value


def _docker_prefix(workspace: Path, canonical: Path, store_mount: Path) -> list[str]:
    """The #146 Docker grant and mounts, with only per-run paths substituted."""
    return ["run", "--rm", "-i", "--pull=never", "--network", "bridge",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--pids-limit", "128", "--memory", "1g", "--user", "10001:10001",
            "--mount", f"type=volume,source={VOLUME},target=/home/runner/.codex",
            "--mount", f"type=bind,source={workspace},target=/draft",
            "--mount", f"type=bind,source={canonical},target=/canonical,readonly",
            "--mount", f"type=bind,source={store_mount},target=/store",
            "--mount", f"type=bind,source={CONFIG},target=/config.toml,readonly",
            "--workdir", "/draft", IMAGE, "sh", "-c",
            'cp /config.toml /home/runner/.codex/config.toml && exec codex "$@"',
            "bootstrap", "app-server", "--stdio"]


class AppServer:
    def __init__(self, command: list[str], evidence: Path):
        self.events = []
        self.messages = queue.Queue()
        self.log = (evidence / "raw-events.jsonl").open("a", encoding="utf-8")
        self.stderr = (evidence / "stderr.log").open("a", encoding="utf-8")
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=self.stderr,
                                        text=True, encoding="utf-8")
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        self.seq = 0

    def _read(self):
        for line in self.process.stdout:
            self.log.write(line)
            self.log.flush()
            try:
                self.messages.put(json.loads(line))
            except json.JSONDecodeError:
                self.events.append({"method": "invalid/json"})

    def request(self, method: str, params: dict, timeout: float = 30) -> dict:
        self.seq += 1
        request_id = self.seq
        self.process.stdin.write(json.dumps({"id": request_id, "method": method,
                                             "params": params}) + "\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                msg = self.messages.get(timeout=min(.5, deadline - time.monotonic()))
            except queue.Empty:
                if self.process.poll() is not None:
                    raise RunnerError("app_server_exited")
                continue
            if msg.get("id") == request_id and "method" not in msg:
                return msg
            self.events.append(msg)
        raise RunnerError("request_timeout:" + method)

    def notify(self, method: str, params: dict) -> None:
        self.process.stdin.write(json.dumps({"method": method, "params": params}) + "\n")
        self.process.stdin.flush()

    def wait_turn(self, turn_id: str, timeout: float, cancelled: threading.Event) -> tuple[str, str | None]:
        deadline = time.monotonic() + timeout
        cursor = 0
        while time.monotonic() < deadline:
            for event in self.events[cursor:]:
                if event.get("method") == "turn/completed":
                    turn = event.get("params", {}).get("turn") or {}
                    if turn.get("id") == turn_id:
                        return turn.get("status") or "unknown", None
            cursor = len(self.events)
            if cancelled.is_set():
                return "cancelled", None
            try:
                msg = self.messages.get(timeout=min(.25, deadline - time.monotonic()))
            except queue.Empty:
                if self.process.poll() is not None:
                    return "failed", "app_server_exited"
                continue
            self.events.append(msg)
        return "timeout", "turn_timeout"

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.reader.join(timeout=5)
        self.log.close()
        self.stderr.close()


def _answer(events: list[dict]) -> str | None:
    answers = []
    for event in events:
        if event.get("method") != "item/completed":
            continue
        item = event.get("params", {}).get("item") or {}
        if item.get("type") == "agentMessage" and isinstance(item.get("text"), str):
            answers.append(item["text"])
    return answers[-1] if answers else None


class LocalRunner:
    def __init__(self, state: Path, skill_store: Path, source_workspace: Path, *, transport=AppServer,
                 check_docker: bool = True, max_model_turns: int = 0):
        self.state = _private(state)
        self.store = SkillStore(skill_store)
        self.source = source_workspace.expanduser().resolve()
        if not self.source.is_dir() or not _git_tree(self.source) or (self.source / ".git").exists():
            raise RunnerError("source_workspace_must_be_git_tree")
        if self.state == self.store.root or self.state.is_relative_to(self.store.root):
            raise RunnerError("state_overlaps_skill_store")
        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / "runs").mkdir(exist_ok=True)
        for record_path in (self.state / "runs").glob("*/record.json"):
            record = _read(record_path)
            if record.get("status") == "running":
                record["status"] = "interrupted"
                record["error_category"] = "runner_restarted"
                _json(record_path, record)
        self.transport = transport
        if not isinstance(max_model_turns, int) or max_model_turns < 0:
            raise RunnerError("invalid_turn_cap")
        self.max_model_turns = max_model_turns
        self.lock = threading.Lock()
        self.cancel_flags = {}
        if hashlib.sha256(CONFIG.read_bytes()).hexdigest() != CONFIG_SHA256:
            raise RunnerError("permission_config_changed")
        if check_docker:
            found = subprocess.run(["docker", "image", "inspect", IMAGE,
                                    "--format", "{{.Id}}"], check=True,
                                   capture_output=True, text=True, timeout=15)
            if found.stdout.strip() != IMAGE_ID:
                raise RunnerError("docker_image_digest_changed")
            subprocess.run(["docker", "volume", "inspect", VOLUME], check=True,
                           capture_output=True, timeout=15)

    def preflight(self) -> dict:
        """Check the existing Docker app-server and advertised models without a turn."""
        root = self.state / "preflight" / str(uuid4())
        root.mkdir(parents=True)
        for name in ("workspace", "canonical", "store"):
            (root / name).mkdir()
        (root / "canonical/sentinel.txt").write_text("CANONICAL-ORIGINAL", encoding="utf-8")
        (root / "store/sentinel.txt").write_text("STORE-ORIGINAL", encoding="utf-8")
        server = None
        try:
            server = self.transport(["docker", *_docker_prefix(
                root / "workspace", root / "canonical", root / "store")], root)
            initialized = server.request("initialize", {"clientInfo": {
                "name": "laomedo_local_runner", "title": "Laomedo Local Runner",
                "version": "0.1.0"}})
            if "result" not in initialized:
                raise RunnerError("initialize_rejected")
            server.notify("initialized", {})
            models = server.request("model/list", {})
            if "result" not in models:
                raise RunnerError("model_list_rejected")
            checks = {}
            for label, command in (
                    ("workspace_write", "printf CANARY > /draft/canary.txt"),
                    ("canonical_write", "printf FORBIDDEN > /canonical/sentinel.txt"),
                    ("store_write", "printf FORBIDDEN > /store/sentinel.txt"),
                    ("auth_read", "cat /home/runner/.codex/auth.json >/dev/null")):
                response = server.request("command/exec", {
                    "command": ["sh", "-c", command], "cwd": "/draft",
                    "timeoutMs": 15000}, timeout=25)
                checks[label] = (response.get("result") or {}).get("exitCode")
            if not (checks["workspace_write"] == 0 and
                    all(checks[x] not in (None, 0) for x in
                        ("canonical_write", "store_write", "auth_read")) and
                    (root / "workspace/canary.txt").read_text() == "CANARY" and
                    (root / "canonical/sentinel.txt").read_text() ==
                    "CANONICAL-ORIGINAL" and
                    (root / "store/sentinel.txt").read_text() == "STORE-ORIGINAL"):
                raise RunnerError("permission_preflight_failed")
            return {"status": "ready", "models": [{
                "id": x.get("id"), "efforts": [
                    y.get("reasoningEffort") if isinstance(y, dict) else y
                    for y in x.get("supportedReasoningEfforts", [])]}
                for x in models["result"].get("data", [])],
                "image": IMAGE, "image_id": IMAGE_ID, "cli_version": CLI_VERSION,
                "profile": VOLUME,
                "config_sha256": CONFIG_SHA256, "permission_checks": checks,
                "submitted_turns": 0}
        finally:
            if server is not None:
                server.close()

    def _run_dir(self, run_id: str) -> Path:
        return self.state / "runs" / _id(run_id)

    def _reserve_turn(self) -> int:
        ledger = self.state / "turn-ledger.json"
        value = _read(ledger) if ledger.exists() else {"attempted_turns": 0}
        count = value.get("attempted_turns")
        if not isinstance(count, int) or count < 0:
            raise RunnerError("invalid_turn_ledger")
        if count >= self.max_model_turns:
            raise RunnerError("model_turn_cap_reached")
        _json(ledger, {"attempted_turns": count + 1,
                       "max_authorized_turns": self.max_model_turns})
        return count + 1

    def _turn_available(self) -> None:
        ledger = self.state / "turn-ledger.json"
        value = _read(ledger) if ledger.exists() else {"attempted_turns": 0}
        count = value.get("attempted_turns")
        if not isinstance(count, int) or count < 0:
            raise RunnerError("invalid_turn_ledger")
        if count >= self.max_model_turns:
            raise RunnerError("model_turn_cap_reached")

    def status(self, run_id: str) -> dict:
        return _read(self._run_dir(run_id) / "record.json")

    def cancel(self, run_id: str) -> dict:
        record = self.status(run_id)
        if record["status"] == "running":
            flag = self.cancel_flags.get(run_id)
            if flag is None:
                raise RunnerError("run_not_active_in_this_process")
            flag.set()
            return {**record, "cancel_requested": True}
        return record

    def _materialize(self, workspace: Path, ref: dict) -> dict:
        if not isinstance(ref, dict) or not all(ref.get(k) for k in
                                                  ("skill_id", "revision_id", "tree_hash")):
            raise RunnerError("pinned_skill_ref_required")
        if ref["revision_id"] != ref["tree_hash"]:
            raise RunnerError("skill_ref_hash_mismatch")
        record = self.store.revision(ref["skill_id"], ref["revision_id"])
        if record["tree_hash"] != ref["tree_hash"]:
            raise RunnerError("skill_ref_hash_mismatch")
        target = workspace / ".agents" / "skills" / ref["skill_id"]
        if target.exists():
            raise RunnerError("skill_path_conflict")
        target.mkdir(parents=True)
        for relative, expected in record["file_hashes"].items():
            item = self.store.read_file(ref["skill_id"], ref["revision_id"], relative)
            if item["file_hash"] != expected:
                raise RunnerError("skill_file_hash_mismatch")
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(item["content"])
        if tree_hash(inventory(target)) != ref["tree_hash"]:
            raise RunnerError("materialized_skill_mismatch")
        return {"skill_id": ref["skill_id"], "revision_id": ref["revision_id"],
                "tree_hash": ref["tree_hash"], "file_hashes": record["file_hashes"],
                "delivery_mode": "project_discovery", "use_evidence": "offered"}

    def start(self, request: dict) -> dict:
        if not isinstance(request, dict):
            raise RunnerError("invalid_request")
        task = request.get("task")
        if not isinstance(task, str) or not task.strip() or len(task) > 16000:
            raise RunnerError("invalid_task")
        model, effort = request.get("model"), request.get("effort")
        if not all(isinstance(x, str) and x for x in (model, effort)):
            raise RunnerError("model_and_effort_required")
        if "skill_refs" in request and "skill_ref" in request:
            raise RunnerError("conflicting_skill_inputs")
        refs = request.get("skill_refs", [request.get("skill_ref")])
        if not isinstance(refs, list) or not 1 <= len(refs) <= 16:
            raise RunnerError("one_to_sixteen_skills_required")
        seen = set()
        for ref in refs:
            if not isinstance(ref, dict) or not isinstance(ref.get("skill_id"), str):
                raise RunnerError("pinned_skill_ref_required")
            if ref["skill_id"] in seen:
                raise RunnerError("duplicate_skill_id")
            seen.add(ref["skill_id"])
        source = self.source
        handoff = self._handoff(request.get("handoff"))
        run_id = str(uuid4())
        run_dir = self._run_dir(run_id)
        run_dir.mkdir()
        workspace, canonical, store_mount = (run_dir / x for x in
                                              ("workspace", "canonical", "store"))
        try:
            source_hash = _copy_tree(source, workspace)
            # Preserve the tested read-only canonical and sibling store mounts.
            if _copy_tree(source, canonical) != source_hash:
                raise RunnerError("source_changed_during_snapshot")
            store_mount.mkdir()
            (store_mount / "sentinel.txt").write_text("STORE-ORIGINAL", encoding="utf-8")
            skills = [self._materialize(workspace, ref) for ref in refs]
            artifacts = import_selected(request.get("artifact_refs", []), workspace,
                                        self._artifact_source, _hash_tree)
            effective_hash = _hash_tree(workspace)
            (run_dir / "raw-events.jsonl").touch()
            record = {"schema_version": 1, "run_id": run_id, "status": "prepared",
                      "error_category": None, "source_hash": source_hash,
                      "effective_hash": effective_hash, "post_run_hash": None,
                      "input_hash": "sha256:" + hashlib.sha256(task.encode()).hexdigest(),
                      "skill": skills[0] if len(skills) == 1 else None,
                      "skills": skills,
                      "provider": getattr(self, "provider", "codex"),
                      "handoff": handoff, "imported_artifacts": artifacts,
                      "requested_model": model, "requested_effort": effort,
                      "effective_model": None, "effective_effort": None,
                      "profile": VOLUME, "image": IMAGE, "image_id": IMAGE_ID,
                      "cli_version": CLI_VERSION,
                      "config_sha256": CONFIG_SHA256, "thread_id": None,
                      "turns": [], "answer": None, "output_ref": None,
                      "raw_event_ref": f"laomedo:run:{run_id}:events"}
            _json(run_dir / "record.json", record)
        except Exception:
            shutil.rmtree(run_dir)
            raise
        return self._execute(run_id, task, resume=False)

    def _artifact_source(self, provider, run_id):
        if provider != getattr(self, "provider", "codex"):
            raise ArtifactError("foreign_artifact_store_required")
        return self._run_dir(run_id) / "post-run", self.status(run_id)

    def select_artifacts(self, run_id, paths):
        if not isinstance(paths, list) or len(paths) > 32:
            raise ArtifactError("invalid_artifact_selection")
        record = self.status(run_id)
        snapshot = self._run_dir(run_id) / "post-run"
        if record.get("status") != "completed" or _hash_tree(snapshot) != record.get("post_run_hash"):
            raise ArtifactError("artifact_snapshot_mismatch")
        result = []
        for path in paths:
            path = relative_path(path)
            source = snapshot / path
            if not source.is_file() or source.stat().st_size > 1024 * 1024:
                raise ArtifactError("artifact_file_missing_or_too_large")
            result.append({"provider": getattr(self, "provider", "codex"), "run_id": run_id,
                "snapshot_hash": record["post_run_hash"], "path": path,
                "content_hash": "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest(),
                "destination": "handoff/" + path})
        if _hash_tree(snapshot) != record["post_run_hash"]:
            raise ArtifactError("artifact_source_changed_during_selection")
        return selections(result)

    def _handoff(self, value):
        if value is None:
            return None
        if not isinstance(value, dict) or set(value) != {"execution_id", "step", "source", "workspace_policy"}:
            raise RunnerError("invalid_handoff_provenance")
        _id(value["execution_id"])
        if type(value["step"]) is not int or value["step"] < 0 or value["workspace_policy"] != "independent":
            raise RunnerError("invalid_handoff_provenance")
        origin = value["source"]
        if origin is not None:
            if not isinstance(origin, dict) or set(origin) != {"provider", "run_id"} or origin["provider"] not in {"codex", "opencode"}:
                raise RunnerError("invalid_handoff_origin")
            _id(origin["run_id"])
        return json.loads(json.dumps(value))

    def resume(self, run_id: str, task: str, *, expected_post_run_hash: str,
               expected_thread_id: str, model: str, effort: str) -> dict:
        record = self.status(run_id)
        if not isinstance(task, str) or not task.strip():
            raise RunnerError("invalid_task")
        if (record["status"] != "completed" or not record["thread_id"] or
                record["thread_id"] != expected_thread_id or
                record["post_run_hash"] != expected_post_run_hash or
                record["requested_model"] != model or record["requested_effort"] != effort or
                record["profile"] != VOLUME or record["image"] != IMAGE or
                record["image_id"] != IMAGE_ID or record["cli_version"] != CLI_VERSION or
                record["config_sha256"] != CONFIG_SHA256):
            raise RunnerError("resume_binding_mismatch")
        run_dir = self._run_dir(run_id)
        snapshot = run_dir / "post-run"
        workspace = run_dir / "workspace"
        if not snapshot.exists() or _hash_tree(snapshot) != expected_post_run_hash:
            raise RunnerError("post_run_snapshot_mismatch")
        if _hash_tree(workspace) != expected_post_run_hash:
            raise RunnerError("workspace_changed_since_snapshot")
        if (_hash_tree(run_dir / "canonical") != record["source_hash"] or
                (run_dir / "store/sentinel.txt").read_text(encoding="utf-8") !=
                "STORE-ORIGINAL"):
            raise RunnerError("protected_mount_changed")
        return self._execute(run_id, task, resume=True)

    def _execute(self, run_id: str, task: str, *, resume: bool) -> dict:
        if not self.lock.acquire(blocking=False):
            raise RunnerError("runner_busy")
        run_dir = self._run_dir(run_id)
        record = self.status(run_id)
        cancelled = threading.Event()
        self.cancel_flags[run_id] = cancelled
        server = None
        try:
            record["status"] = "running"
            _json(run_dir / "record.json", record)
            server = self.transport(["docker", *_docker_prefix(
                run_dir / "workspace", run_dir / "canonical", run_dir / "store")], run_dir)
            initialized = server.request("initialize", {"clientInfo": {
                "name": "laomedo_local_runner", "title": "Laomedo Local Runner",
                "version": "0.1.0"}})
            if "result" not in initialized:
                raise RunnerError("initialize_rejected")
            server.notify("initialized", {})
            models = server.request("model/list", {})
            entries = (models.get("result") or {}).get("data") or []
            choice = next((x for x in entries if x.get("id") == record["requested_model"]), None)
            levels = {item.get("reasoningEffort") if isinstance(item, dict) else item
                      for item in (choice or {}).get("supportedReasoningEfforts", [])}
            if choice is None or record["requested_effort"] not in levels:
                raise RunnerError("unsupported_model_effort")
            self._turn_available()
            method = "thread/resume" if resume else "thread/start"
            params = ({"threadId": record["thread_id"], "cwd": "/draft"} if resume else
                      {"model": record["requested_model"], "cwd": "/draft",
                       "approvalPolicy": "never"})
            response = server.request(method, params)
            result = response.get("result") or {}
            thread = result.get("thread") or {}
            native_id = thread.get("id")
            if not native_id or (resume and native_id != record["thread_id"]):
                raise RunnerError("thread_identity_mismatch")
            record["thread_id"] = native_id
            record["effective_model"] = thread.get("model") or result.get("model")
            record["effective_effort"] = (result.get("reasoningEffort") or
                                          thread.get("reasoningEffort"))
            _json(run_dir / "record.json", record)
            attempt = self._reserve_turn()
            record["attempt_number"] = attempt
            _json(run_dir / "record.json", record)
            sent = server.request("turn/start", {"threadId": native_id,
                "model": record["requested_model"], "effort": record["requested_effort"],
                "cwd": "/draft", "input": [{"type": "text", "text": task}]})
            turn_id = ((sent.get("result") or {}).get("turn") or {}).get("id")
            if not turn_id:
                raise RunnerError("turn_dispatch_rejected")
            status, error = server.wait_turn(turn_id, 180, cancelled)
            record["turns"].append({"turn_id": turn_id, "status": status,
                                    "error_category": error,
                                    "input_hash": "sha256:" +
                                    hashlib.sha256(task.encode()).hexdigest()})
            record["status"] = "completed" if status == "completed" else status
            record["error_category"] = error
            record["answer"] = _answer(server.events) if status == "completed" else None
            if status == "completed" and not record["answer"]:
                raise RunnerError("completed_without_agent_message")
            if status == "completed":
                post_hash = _hash_tree(run_dir / "workspace")
                pending = run_dir / ("post-run-pending-" + uuid4().hex)
                _copy_tree(run_dir / "workspace", pending)
                old = run_dir / "post-run"
                if old.exists():
                    shutil.rmtree(old)
                pending.rename(old)
                record["post_run_hash"] = post_hash
                record["output_ref"] = f"laomedo:run:{run_id}:workspace"
            if (_hash_tree(run_dir / "canonical") != record["source_hash"] or
                    (run_dir / "store/sentinel.txt").read_text(encoding="utf-8") !=
                    "STORE-ORIGINAL"):
                raise RunnerError("protected_mount_changed")
        except Exception as exc:
            record["status"] = "failed"
            record["error_category"] = str(exc) if isinstance(exc, RunnerError) else type(exc).__name__
        finally:
            if server is not None:
                server.close()
            _json(run_dir / "record.json", record)
            self.cancel_flags.pop(run_id, None)
            self.lock.release()
        return record


def serve(runner: LocalRunner, host: str = "127.0.0.1", port: int = 8765):
    if host not in ("127.0.0.1", "::1"):
        raise RunnerError("loopback_only")

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, code: int, value: dict):
            data = json.dumps(value).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self):
            if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                raise RunnerError("json_content_type_required")
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > MAX_BODY:
                raise RunnerError("invalid_body_size")
            return json.loads(self.rfile.read(length))

        def do_GET(self):
            try:
                parts = self.path.strip("/").split("/")
                if len(parts) != 3 or parts[:2] != ["v1", "runs"]:
                    raise RunnerError("unknown_endpoint")
                self._reply(200, runner.status(parts[2]))
            except (RunnerError, ValueError, OSError) as exc:
                self._reply(404, {"status": "failed", "error_category": str(exc)})

        def do_POST(self):
            try:
                parts = self.path.strip("/").split("/")
                body = self._body()
                if parts == ["v1", "runs"]:
                    result = runner.start(body)
                elif len(parts) == 4 and parts[:2] == ["v1", "runs"] and parts[3] == "resume":
                    result = runner.resume(parts[2], body["task"],
                        expected_post_run_hash=body["expected_post_run_hash"],
                        expected_thread_id=body["expected_thread_id"],
                        model=body["model"], effort=body["effort"])
                elif len(parts) == 4 and parts[:2] == ["v1", "runs"] and parts[3] == "cancel":
                    result = runner.cancel(parts[2])
                elif len(parts) == 4 and parts[:2] == ["v1", "runs"] and parts[3] == "artifacts":
                    result = {"status": "completed", "artifact_refs": runner.select_artifacts(parts[2], body["paths"])}
                else:
                    raise RunnerError("unknown_endpoint")
                code = (202 if result.get("cancel_requested") else
                        200 if result["status"] == "completed" else 502)
                self._reply(code, result)
            except (RunnerError, SkillStoreError, ArtifactError, KeyError, ValueError, OSError) as exc:
                self._reply(400, {"status": "failed", "error_category": str(exc)})

    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--skill-store", type=Path, required=True)
    parser.add_argument("--source-workspace", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--max-model-turns", type=int, default=0)
    args = parser.parse_args()
    runner = LocalRunner(args.state, args.skill_store, args.source_workspace,
                         max_model_turns=args.max_model_turns)
    if args.preflight:
        print(json.dumps(runner.preflight(), indent=2))
        return
    serve(runner, port=args.port).serve_forever()


if __name__ == "__main__":
    main()
