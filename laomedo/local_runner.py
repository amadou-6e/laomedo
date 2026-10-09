"""Single-user local Codex runner backed by the tested Docker profile."""

from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import re
import secrets
import shutil
import stat
import subprocess
import threading
import time
from urllib.request import urlopen
from uuid import UUID, uuid4

from .skill_store import SkillStore, SkillStoreError, inventory, tree_hash
from .artifacts import ArtifactError, import_selected, relative_path, selections
from .container_lease import LABEL_RUN, LABEL_TOKEN, cleanup_exact
from .lease_service import LeaseClient
from .mediation_authority import RunGrantAuthority
from .github_mediation import MediationError
from .git_workspace import GitWorkspaceError, prepare_git_workspace
from .siwc_auth import AuthError, ChatGPTConnection, _outside_git


IMAGE = "laomedo-codex-boundary:0.159.2"
IMAGE_ID = "sha256:7b79ce12be47d6c8262dd4043895112d204416bda5cd891d124775df55587239"
GIT_IMAGE = "laomedo-codex-git:0.159.2"
GIT_IMAGE_ID = "sha256:eceda79a349c46a8afd6fb271e92b979f872ca67cbdf228fde6dee0856481e78"
CLI_VERSION = "codex-cli 0.159.2"
VOLUME = "laomedo-122-docker-auth"
SPLIT_TOOLS = frozenset({
    "apply_patch", "clock__curr_time", "create_goal", "exec_command",
    "get_goal", "update_goal", "view_image", "wait_for_environment",
    "write_stdin",
})
CONFIG = Path(__file__).resolve().parent / "runner-config.toml"
MEDIATION_CLIENT = Path(__file__).resolve().parent / "agent_mediation_client.mjs"
CONFIG_SHA256 = "a14cd7e8abb4216b16d29e55809c2c3c9a9c33cc0196fd459fc033aaaa1ea4c4"
CONFIG_LF_SHA256 = "a1472e6d63ac71307af791767cc22fb76959549d9371114ff3382e4dfb3ad11b"
MAX_BODY = 64 * 1024
MAX_GIT_WORKSPACE_SNAPSHOT_BYTES = 64 * 1024 * 1024
MAX_GIT_WORKSPACE_SNAPSHOT_ENTRIES = 10000
NATIVE_ERROR_KINDS = frozenset({
    "contextWindowExceeded", "sessionBudgetExceeded", "usageLimitExceeded",
    "rateLimitExceeded", "flexUnavailable", "serverOverloaded", "cyberPolicy",
    "misalignmentPolicyViolation", "tooManyDenials", "internalServerError",
    "unauthorized", "badRequest", "threadRollbackFailed", "sandboxError",
    "other", "httpConnectionFailed", "responseStreamConnectionFailed",
    "responseStreamDisconnected", "responseTooManyFailedAttempts",
    "activeTurnNotSteerable",
})
NATIVE_HTTP_ERROR_KINDS = frozenset({
    "httpConnectionFailed", "responseStreamConnectionFailed",
    "responseStreamDisconnected", "responseTooManyFailedAttempts",
})


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
    try:
        # Windows can deny replacement while a concurrent poll has the old
        # record open. Keep the write atomic; only retry that transient lock.
        for attempt in range(20):
            try:
                os.replace(pending, path)
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(.01)
    finally:
        pending.unlink(missing_ok=True)


def _read(path: Path) -> dict:
    # A concurrent atomic replacement can briefly deny a Windows reader.
    for attempt in range(5):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            break
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(.01)
    if not isinstance(value, dict):
        raise RunnerError("invalid_record")
    return value


def _hash_tree(path: Path, *, exclude_root_git: bool = False) -> str:
    """Hash regular files and directories, including empty directories."""
    if not path.is_dir() or path.is_symlink():
        raise RunnerError("invalid_workspace")
    files = {}
    directories = []
    total_bytes = 0
    for parent, dirs, names in os.walk(path, followlinks=False):
        if exclude_root_git and Path(parent) == path:
            dirs[:] = [name for name in dirs if name != ".git"]
            names = [name for name in names if name != ".git"]
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
                if exclude_root_git:
                    total_bytes += item.stat().st_size
                    if (total_bytes > MAX_GIT_WORKSPACE_SNAPSHOT_BYTES or
                            len(files) + len(directories) >=
                            MAX_GIT_WORKSPACE_SNAPSHOT_ENTRIES):
                        raise RunnerError("git_workspace_snapshot_limit")
                files[item.relative_to(path).as_posix()] = item.read_bytes()
            else:
                directories.append(item.relative_to(path).as_posix())
                if exclude_root_git and len(files) + len(directories) > \
                        MAX_GIT_WORKSPACE_SNAPSHOT_ENTRIES:
                    raise RunnerError("git_workspace_snapshot_limit")
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


def _copy_tree(source: Path, target: Path, *, exclude_root_git: bool = False) -> str:
    expected = _hash_tree(source, exclude_root_git=exclude_root_git)
    ignore = (lambda parent, names: {name for name in names
               if Path(parent) == source and name == ".git"}) if exclude_root_git else None
    shutil.copytree(source, target, ignore=ignore)
    if _hash_tree(target) != expected:
        raise RunnerError("workspace_copy_mismatch")
    return expected


def _id(value: str) -> str:
    if str(UUID(value)) != value:
        raise RunnerError("invalid_run_id")
    return value


def _native_error_summary(events: list[dict], turn_id: str) -> dict:
    """Project app-server error events to a closed, nontextual diagnostic schema."""
    counts = {}
    statuses = set()
    retry_events = 0
    error_events = 0
    last_kind = None
    for event in events:
        if event.get("method") != "error":
            continue
        params = event.get("params")
        if not isinstance(params, dict) or params.get("turnId") != turn_id:
            continue
        error_events += 1
        retry_events += params.get("willRetry") is True
        error = params.get("error")
        info = error.get("codexErrorInfo") if isinstance(error, dict) else None
        kind = "unknown"
        if isinstance(info, str) and info in NATIVE_ERROR_KINDS:
            kind = info
        elif isinstance(info, dict) and len(info) == 1:
            candidate, details = next(iter(info.items()))
            if candidate in NATIVE_ERROR_KINDS and isinstance(details, dict):
                kind = candidate
                if candidate in NATIVE_HTTP_ERROR_KINDS:
                    status = details.get("httpStatusCode")
                    if type(status) is int and 100 <= status <= 599:
                        statuses.add(status)
        counts[kind] = counts.get(kind, 0) + 1
        last_kind = kind
    return {"schema_version": 1, "error_events": error_events,
            "retry_events": retry_events, "categories": counts,
            "http_status_codes": sorted(statuses), "last_category": last_kind}


def _auth_record_error(exc: AuthError) -> tuple[str, str]:
    code = str(exc)
    if code == "auth_account_missing":
        return "auth_missing", "missing"
    if code == "auth_consent_denied":
        return "auth_consent_missing", "consent_denied"
    if code == "auth_scope_missing":
        return "auth_scope_denied", "scope_missing"
    if code in {"auth_refresh_unknown", "auth_refresh_lock_unavailable",
                "auth_refresh_response_invalid"}:
        return "auth_refresh_failed", code.removeprefix("auth_")
    if code == "auth_revoked":
        return "auth_revoked", "revoked"
    if code == "auth_account_mismatch":
        return "auth_account_mismatch", "account_mismatch"
    if code == "auth_generation_changed":
        return "auth_generation_changed", "generation_changed"
    return "auth_mode_unavailable", code.removeprefix("auth_")


def _docker_prefix(workspace: Path, canonical: Path, store_mount: Path, *,
                   image: str = IMAGE,
                   name: str | None = None, run_id: str | None = None,
                   launch_token: str | None = None,
                   capability: Path | None = None,
                   mediator_url: str | None = None,
                   mediator_instance: str | None = None,
                   command_directory: Path | None = None,
                   repository: str | None = None,
                   branch: str | None = None) -> list[str]:
    """The #146 Docker grant and mounts, with only per-run paths substituted."""
    name = name or "laomedo-codex-" + uuid4().hex
    labels = (["--label", f"{LABEL_RUN}={run_id}",
               "--label", f"{LABEL_TOKEN}={launch_token}"]
              if run_id and launch_token else [])
    mediation = (["--mount", f"type=bind,source={capability},target=/run/laomedo/capability,readonly",
                  "--mount", f"type=bind,source={MEDIATION_CLIENT},target=/run/laomedo/mediate.mjs,readonly",
                  "--env", "LAOMEDO_MEDIATOR_URL=" + mediator_url,
                  "--env", "LAOMEDO_MEDIATOR_INSTANCE=" + mediator_instance,
                  "--env", "LAOMEDO_CAPABILITY_FILE=/run/laomedo/capability"]
                 if all(value is not None for value in
                        (capability, mediator_url, mediator_instance)) else [])
    if any(value is not None for value in
           (capability, mediator_url, mediator_instance)) and not mediation:
        raise RunnerError("incomplete_mediator_mount")
    if command_directory is not None:
        if not mediation or repository is None or branch is None:
            raise RunnerError("incomplete_command_mount")
        mediation += [
            "--mount", f"type=bind,source={command_directory},target=/run/laomedo/bin,readonly",
            "--mount", f"type=bind,source={MEDIATION_CLIENT.with_name('agent_gh_adapter.mjs')},target=/run/laomedo/gh.mjs,readonly",
            "--mount", f"type=bind,source={MEDIATION_CLIENT.with_name('agent_git_remote.mjs')},target=/run/laomedo/git-remote.mjs,readonly",
            "--env", "LAOMEDO_REPOSITORY=" + repository,
            "--env", "LAOMEDO_RUN_BRANCH=" + branch,
            "--env", "PATH=/run/laomedo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"]
    return ["run", "--rm", "-i", "--name", name, *labels,
            "--pull=never", "--network", "bridge",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--pids-limit", "128", "--memory", "1g", "--user", "10001:10001",
            "--mount", f"type=volume,source={VOLUME},target=/home/runner/.codex",
            "--mount", f"type=bind,source={workspace},target=/draft",
            "--mount", f"type=bind,source={canonical},target=/canonical,readonly",
            "--mount", f"type=bind,source={store_mount},target=/store",
            "--mount", f"type=bind,source={CONFIG},target=/config.toml,readonly",
            *mediation,
            "--workdir", "/draft", image, "sh", "-c",
            'cp /config.toml /home/runner/.codex/config.toml && exec codex "$@"',
            "bootstrap", "app-server", "--stdio"]


class AppServer:
    def __init__(self, command: list[str], evidence: Path, *, env=None,
                 secret_redactions=()):
        self.events = []
        self.messages = queue.Queue()
        self.container_name = command[command.index("--name") + 1]
        self.run_id = None
        self.launch_token = None
        for value in (command[index + 1] for index, item in enumerate(command[:-1])
                      if item == "--label"):
            if value.startswith(LABEL_RUN + "="):
                self.run_id = value.split("=", 1)[1]
            elif value.startswith(LABEL_TOKEN + "="):
                self.launch_token = value.split("=", 1)[1]
        self.active_thread_id = None
        self.interrupt_acknowledged = False
        self.secret_redactions = tuple(value for value in secret_redactions if value)
        self.log = (evidence / "raw-events.jsonl").open("a", encoding="utf-8")
        self.stderr = (evidence / "stderr.log").open("a", encoding="utf-8")
        try:
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE,
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            text=True, encoding="utf-8", env=env)
        except Exception:
            self.log.close()
            self.stderr.close()
            raise
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.stderr_reader = threading.Thread(target=self._read_stderr, daemon=True)
        self.reader.start()
        self.stderr_reader.start()
        self.seq = 0

    def _redact(self, line: str) -> str:
        for secret in self.secret_redactions:
            line = line.replace(secret, "[REDACTED_RUN_CAPABILITY]")
        return line

    def _read(self):
        for line in self.process.stdout:
            line = self._redact(line)
            self.log.write(line)
            self.log.flush()
            try:
                self.messages.put(json.loads(line))
            except json.JSONDecodeError:
                self.events.append({"method": "invalid/json"})

    def _read_stderr(self):
        for line in self.process.stderr:
            self.stderr.write(self._redact(line))
            self.stderr.flush()

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
                self.interrupt(turn_id)
                return "cancelled", "cancelled_by_user"
            try:
                msg = self.messages.get(timeout=min(.25, deadline - time.monotonic()))
            except queue.Empty:
                if self.process.poll() is not None:
                    return "failed", "app_server_exited"
                continue
            self.events.append(msg)
        self.interrupt(turn_id)
        return "timeout", "turn_timeout"

    def interrupt(self, turn_id: str) -> None:
        if not self.active_thread_id:
            return
        try:
            response = self.request("turn/interrupt", {
                "threadId": self.active_thread_id, "turnId": turn_id}, timeout=5)
            self.interrupt_acknowledged = "result" in response and "error" not in response
        except (RunnerError, OSError, ValueError):
            # Forced container removal below remains the authoritative boundary.
            self.interrupt_acknowledged = False

    def close(self) -> None:
        verified = False
        exact = (getattr(self, "run_id", None) is not None and
                 getattr(self, "launch_token", None) is not None)
        try:
            # Stop the owned container promptly, then repeat after the docker
            # client exits to close the startup race before the first removal.
            try:
                if exact:
                    cleanup_exact(self.container_name, self.run_id, self.launch_token)
                else:
                    subprocess.run(["docker", "rm", "-f", self.container_name],
                                   capture_output=True, timeout=15)
            except (OSError, subprocess.TimeoutExpired):
                pass
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            try:
                if exact:
                    verified, _ = cleanup_exact(self.container_name, self.run_id,
                                                self.launch_token)
                else:
                    subprocess.run(["docker", "rm", "-f", self.container_name],
                                   capture_output=True, timeout=15)
                    probe = subprocess.run(["docker", "inspect", self.container_name],
                                           capture_output=True, timeout=10)
                    stderr = probe.stderr or b""
                    if isinstance(stderr, str):
                        stderr = stderr.encode()
                    verified = (probe.returncode != 0 and
                                (b"No such object:" in stderr or b"No such container:" in stderr))
            except (OSError, subprocess.TimeoutExpired):
                verified = False
        finally:
            self.reader.join(timeout=5)
            self.stderr_reader.join(timeout=5)
            self.log.close()
            self.stderr.close()
        if not verified:
            raise RunnerError("container_termination_unverified")


def _docker_checked(*args: str, timeout: float = 15) -> str:
    try:
        result = subprocess.run(["docker", *args], capture_output=True,
                                text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        raise RunnerError("docker_control_unavailable") from None
    if result.returncode:
        raise RunnerError("docker_control_failed")
    return result.stdout.strip()


def _split_profile(state: Path) -> str:
    return "laomedo-codex-split-" + hashlib.sha256(
        str(state).encode("utf-8")).hexdigest()[:20]


def _ensure_split_profile(name: str) -> None:
    found = subprocess.run(["docker", "volume", "inspect", name],
                           capture_output=True, timeout=10)
    if found.returncode == 0:
        return
    _docker_checked("volume", "create", name)
    try:
        _docker_checked("run", "--rm", "--pull=never", "--network", "none",
                        "--user", "0:0", "--cap-drop", "ALL", "--cap-add", "CHOWN",
                        "--mount", f"type=volume,source={name},target=/home/runner/.codex",
                        IMAGE, "chown", "10001:10001", "/home/runner/.codex",
                        timeout=30)
    except Exception:
        _docker_checked("volume", "rm", name)
        raise


class SplitAppServer(AppServer):
    """Pinned Codex controller with a separate, disposable tool executor.

    This mode is credential-free until the app-owned OAuth broker is connected.
    The executor never mounts the controller profile or receives ACCESS_TOKEN.
    """

    def __init__(self, workspace: Path, canonical: Path, store_mount: Path,
                 evidence: Path, profile: str, *, provider_config=(),
                 access_token=None):
        self.executor_name = "laomedo-executor-" + uuid4().hex
        self.environment_id = "laomedo-executor-" + uuid4().hex
        self.executor_token = secrets.token_hex(32)
        self.registered = False
        self.authorization_probe = None
        self._controller_started = False
        self._executor_started = False
        if _docker_checked("image", "inspect", IMAGE, "--format",
                           "{{.Id}}") != IMAGE_ID:
            raise RunnerError("docker_image_digest_changed")
        executor = ["run", "--rm", "-d", "--name", self.executor_name,
                    "--pull=never", "--network", "bridge",
                    "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                    "--pids-limit", "128", "--memory", "1g", "--user", "10001:10001",
                    "--mount", f"type=bind,source={workspace},target=/draft",
                    "--tmpfs", "/home/runner/.codex:rw,uid=10001,gid=10001,mode=0700",
                    "--workdir", "/draft", IMAGE, "codex", "exec-server",
                    "--listen", "ws://0.0.0.0:39871", "--ws-auth", "capability-token",
                    "--ws-token-sha256",
                    hashlib.sha256(self.executor_token.encode()).hexdigest()]
        try:
            _docker_checked(*executor, timeout=30)
            self._executor_started = True
            command = _docker_prefix(workspace, canonical, store_mount)
            command[command.index("--network") + 1] = "container:" + self.executor_name
            old_mount = f"type=volume,source={VOLUME},target=/home/runner/.codex"
            index = command.index(old_mount)
            del command[index - 1:index + 1]
            command[command.index("--workdir"):command.index("--workdir")] = [
                "--mount", f"type=volume,source={profile},target=/home/runner/.codex"]
            command += ["-c", "features.deferred_executor=true",
                        "-c", "features.executor_capability_discovery=true"]
            for setting in provider_config:
                command += ["-c", setting]
            environment = None
            if access_token is not None:
                if not isinstance(access_token, str) or not access_token:
                    raise RunnerError("invalid_controller_token")
                command[command.index("--workdir"):command.index("--workdir")] = [
                    "--env", "ACCESS_TOKEN"]
                environment = dict(os.environ, ACCESS_TOKEN=access_token)
            super().__init__(["docker", *command], evidence, env=environment)
            self._controller_started = True
        except Exception:
            if self._executor_started:
                subprocess.run(["docker", "rm", "-f", self.executor_name],
                               capture_output=True, timeout=15)
            raise

    def _controller_listeners(self) -> set[str]:
        """Reject controller-owned listening TCP/Unix and any UDP socket."""
        fds = _docker_checked("exec", self.container_name, "sh", "-c",
                              "ls -l /proc/[0-9]*/fd 2>/dev/null", timeout=5)
        owned = set(re.findall(r"socket:\[(\d+)\]", fds))
        if not owned:
            return set()
        found = set()
        for table, kind in (("tcp", "tcp"), ("tcp6", "tcp"),
                            ("udp", "udp"), ("udp6", "udp")):
            rows = _docker_checked("exec", self.container_name, "cat",
                                   "/proc/net/" + table, timeout=5)
            for row in rows.splitlines()[1:]:
                fields = row.split()
                if len(fields) > 9 and fields[9] in owned and (
                        kind == "udp" or fields[3] == "0A"):
                    found.add(kind)
        rows = _docker_checked("exec", self.container_name, "cat",
                               "/proc/net/unix", timeout=5)
        for row in rows.splitlines()[1:]:
            fields = row.split()
            if (len(fields) > 6 and fields[6] in owned and
                    int(fields[3], 16) & 0x10000):
                found.add("unix")
        return found

    def assert_controller_isolated(self) -> None:
        if self._controller_listeners():
            raise RunnerError("controller_listener_gate_failed")
        if _docker_checked("exec", self.container_name, "codex", "--version",
                           timeout=5) != CLI_VERSION:
            raise RunnerError("unsupported_codex_cli_version")
        if _docker_checked("inspect", self.executor_name, "--format",
                           "{{.State.Running}}", timeout=5) != "true":
            raise RunnerError("executor_not_running")
        for name in (self.container_name, self.executor_name):
            if _docker_checked("inspect", name, "--format", "{{.Image}}",
                               timeout=5) != IMAGE_ID:
                raise RunnerError("running_image_digest_changed")

    def register_executor(self) -> None:
        self.assert_controller_isolated()
        response = self.request("environment/add", {
            "environmentId": self.environment_id,
            "execServerUrl": "ws://127.0.0.1:39871",
            "authBearerToken": self.executor_token,
            "connectTimeoutMs": 15000}, timeout=25)
        if "result" not in response or "error" in response:
            raise RunnerError("executor_registration_rejected")
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            response = self.request("environment/status", {
                "environmentId": self.environment_id}, timeout=5)
            status = (response.get("result") or {}).get("status")
            if status == "ready":
                self.registered = True
                return
            if status != "pending":
                break
            time.sleep(.2)
        raise RunnerError("executor_not_ready")

    def thread_environment(self) -> list[dict]:
        if not self.registered:
            raise RunnerError("executor_not_registered")
        selection = [{"environmentId": self.environment_id, "cwd": "/draft"}]
        self.assert_executor_selection(selection)
        return selection

    def turn_environment(self) -> list[dict]:
        if not self.registered:
            raise RunnerError("executor_not_registered")
        selection = [{"environmentId": self.environment_id, "cwd": "/draft",
                      "runtimeWorkspaceRoots": ["/draft"]}]
        self.assert_executor_selection(selection)
        return selection

    def assert_executor_selection(self, selection: list[dict]) -> None:
        """Refuse a missing or ambiguous remote tool route before dispatch."""
        if (len(selection) != 1 or
                selection[0].get("environmentId") != self.environment_id or
                selection[0].get("cwd") != "/draft"):
            raise RunnerError("executor_selection_mismatch")

    def wait_turn(self, turn_id: str, timeout: float,
                  cancelled: threading.Event) -> tuple[str, str | None]:
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
                self.interrupt(turn_id)
                return "cancelled", "cancelled_by_user"
            if self.authorization_probe is not None and not self.authorization_probe():
                self.interrupt(turn_id)
                return "unknown", "auth_revoked_during_turn"
            try:
                if _docker_checked("inspect", self.executor_name, "--format",
                                   "{{.State.Running}}", timeout=3) != "true":
                    return "unknown", "executor_lost"
            except RunnerError:
                return "unknown", "executor_lost"
            try:
                msg = self.messages.get(timeout=min(.25, deadline - time.monotonic()))
            except queue.Empty:
                if self.process.poll() is not None:
                    return "unknown", "controller_exited"
                continue
            self.events.append(msg)
        self.interrupt(turn_id)
        return "timeout", "turn_timeout"

    def close(self) -> None:
        error = None
        try:
            if self._controller_started:
                super().close()
        except RunnerError as exc:
            error = exc
        finally:
            try:
                if self._executor_started:
                    _docker_checked("rm", "-f", self.executor_name, timeout=15)
                    check = subprocess.run(["docker", "inspect", self.executor_name],
                                           capture_output=True, timeout=10)
                    if (check.returncode == 0 or not any(
                            marker in check.stderr for marker in
                            (b"No such object:", b"No such container:"))):
                        raise RunnerError("executor_termination_unverified")
            except RunnerError as exc:
                error = error or exc
        if error:
            raise error


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
                 check_docker: bool = True, max_model_turns: int = 0,
                 supervise_containers: bool | None = None,
                 lease_service: Path | None = None,
                 github_authority: RunGrantAuthority | None = None,
                 mediator_state: Path | None = None,
                 git_workspace: bool = False,
                 split_executor: bool = False, split_provider_config=(),
                 split_access_token=None, auth_store: Path | None = None):
        self.state = _private(state)
        self.store = SkillStore(skill_store)
        self.source = source_workspace.expanduser().resolve()
        self.git_workspace = git_workspace
        self.image = GIT_IMAGE if git_workspace else IMAGE
        self.image_id = GIT_IMAGE_ID if git_workspace else IMAGE_ID
        if not self.source.is_dir() or (self.source / ".git").is_dir() != git_workspace or \
                (not git_workspace and not _git_tree(self.source)):
            raise RunnerError("source_workspace_must_be_git_tree")
        if self.state == self.store.root or self.state.is_relative_to(self.store.root):
            raise RunnerError("state_overlaps_skill_store")
        self.state.mkdir(parents=True, exist_ok=True)
        token_path = self.state / "api-token"
        try:
            fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as token_file:
                token_file.write(secrets.token_hex(32))
        self.api_token = token_path.read_text(encoding="utf-8")
        if not re.fullmatch(r"[0-9a-f]{64}", self.api_token):
            raise RunnerError("invalid_runner_api_token")
        (self.state / "runs").mkdir(exist_ok=True)
        self.supervise_containers = (transport is AppServer and not split_executor
                                     if supervise_containers is None
                                     else supervise_containers)
        if split_executor and self.supervise_containers:
            raise RunnerError("split_executor_lease_unavailable")
        if git_workspace and split_executor:
            raise RunnerError("git_workspace_split_unsupported")
        # The lease service is started independently of this runner, so a
        # whole-process-tree kill of the runner cannot also kill it.
        self.lease_service = Path(lease_service).resolve() if lease_service else None
        self.github_authority = github_authority
        self.mediator_state = _private(mediator_state) if mediator_state else None
        for record_path in (self.state / "runs").glob("*/record.json"):
            record = _read(record_path)
            if record.get("status") in {"prepared", "running"}:
                record["status"] = "interrupted"
                record["error_category"] = "runner_restarted"
                owner = record.get("container_ownership") or {}
                if owner.get("supervised"):
                    verified, detail = cleanup_exact(owner["name"], record["run_id"],
                                                     owner["launch_token"])
                    owner["cleanup_verified"] = verified
                    owner["cleanup_detail"] = detail
                    if not verified:
                        record["error_category"] = "container_cleanup_unverified"
                _json(record_path, record)
        self.transport = transport
        self.split_executor = split_executor
        self.split_provider_config = tuple(split_provider_config)
        self.split_access_token = split_access_token
        if auth_store is not None and not split_executor:
            raise RunnerError("app_owned_auth_requires_split_executor")
        if auth_store is not None and (split_provider_config or split_access_token):
            raise RunnerError("conflicting_split_auth_sources")
        if auth_store is not None:
            auth_root = _outside_git(auth_store)
            if (auth_root == self.state or auth_root.is_relative_to(self.state) or
                    self.state.is_relative_to(auth_root) or
                    auth_root == self.store.root or
                    auth_root.is_relative_to(self.store.root) or
                    self.store.root.is_relative_to(auth_root)):
                raise RunnerError("auth_store_overlaps_runner_state")
            self.auth = ChatGPTConnection(auth_root)
        else:
            self.auth = None
        self.instance_id = str(uuid4())
        if self.auth:
            self.split_provider_config = (
                'model_provider="openai_chatgpt_plan"',
                'model_providers.openai_chatgpt_plan.name="ChatGPT plan"',
                'model_providers.openai_chatgpt_plan.base_url="https://api.openai.com/v1"',
                'model_providers.openai_chatgpt_plan.env_key="ACCESS_TOKEN"',
                'model_providers.openai_chatgpt_plan.wire_api="responses"',
                'model_providers.openai_chatgpt_plan.requires_openai_auth=false',
                'model_providers.openai_chatgpt_plan.supports_websockets=false',
            )
        self.profile = _split_profile(self.state) if split_executor else VOLUME
        if split_executor and transport is not AppServer:
            raise RunnerError("split_executor_requires_native_transport")
        if (self.split_provider_config or split_access_token is not None) and not split_executor:
            raise RunnerError("split_provider_requires_split_executor")
        if not isinstance(max_model_turns, int) or max_model_turns < 0:
            raise RunnerError("invalid_turn_cap")
        self.max_model_turns = max_model_turns
        self.lock = threading.Lock()
        self.control_lock = threading.Lock()
        self.request_lock = threading.Lock()
        self.cancel_flags = {}
        # The checked-in policy is LF on Linux and CRLF in Windows worktrees.
        # Accept only these two reviewed byte representations of the same policy.
        if hashlib.sha256(CONFIG.read_bytes()).hexdigest() not in {CONFIG_SHA256, CONFIG_LF_SHA256}:
            raise RunnerError("permission_config_changed")
        if check_docker:
            found = subprocess.run(["docker", "image", "inspect", self.image,
                                    "--format", "{{.Id}}"], check=True,
                                   capture_output=True, text=True, timeout=15)
            if found.stdout.strip() != self.image_id:
                raise RunnerError("docker_image_digest_changed")
            if not split_executor:
                subprocess.run(["docker", "volume", "inspect", VOLUME], check=True,
                               capture_output=True, timeout=15)
            else:
                _ensure_split_profile(self.profile)

    def _open_server(self, root: Path, *, access_token=None,
                     name: str | None = None, run_id: str | None = None,
                     launch_token: str | None = None,
                     capability: Path | None = None,
                     mediator_url: str | None = None,
                     mediator_instance: str | None = None,
                     repository: str | None = None,
                     branch: str | None = None):
        workspace, canonical, store_mount = (root / name for name in
                                              ("workspace", "canonical", "store"))
        if self.split_executor:
            return SplitAppServer(workspace, canonical, store_mount, root,
                                  self.profile,
                                  provider_config=self.split_provider_config,
                                  access_token=(access_token if access_token is not None
                                                else self.split_access_token))
        command_directory = None
        if capability is not None and self.git_workspace:
            from .agent_cli import prepare_commands, configure_remote
            if repository is None or branch is None:
                raise RunnerError("mediated_command_scope_missing")
            command_directory = prepare_commands(root, repository, branch)
            # The checkout was prepared without a provider remote. This is a
            # credential-free helper URL, not an HTTPS fallback.
            configure_remote(workspace, repository)
        # Launch the opt-in image by its verified ID, not a mutable local tag.
        command = ["docker", *_docker_prefix(
            workspace, canonical, store_mount,
            image=self.image_id if self.git_workspace else self.image,
            name=name, run_id=run_id,
            launch_token=launch_token, capability=capability,
            mediator_url=mediator_url,
            mediator_instance=mediator_instance, command_directory=command_directory,
            repository=repository, branch=branch)]
        if capability is not None and self.transport is AppServer:
            return self.transport(command, root, secret_redactions=(
                capability.read_text(encoding="utf-8").strip(),))
        return self.transport(command, root)

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
            token = self.auth.access_token()[0] if self.auth else None
            server = self._open_server(root, access_token=token)
            initialized = server.request("initialize", {"clientInfo": {
                "name": "laomedo_local_runner", "title": "Laomedo Local Runner",
                "version": "0.1.0"},
                **({"capabilities": {"experimentalApi": True}}
                   if self.split_executor else {})})
            if "result" not in initialized:
                raise RunnerError("initialize_rejected")
            server.notify("initialized", {})
            if self.split_executor:
                server.register_executor()
            models = server.request("model/list", {})
            if "result" not in models:
                raise RunnerError("model_list_rejected")
            checks = {}
            if self.split_executor:
                # Direct checks against the tool executor. Calling command/exec
                # on app-server would execute inside the credential controller.
                for label, command in (
                        ("workspace_write", "printf CANARY > /draft/canary.txt"),
                        ("canonical_write", "printf FORBIDDEN > /canonical/sentinel.txt"),
                        ("store_write", "printf FORBIDDEN > /store/sentinel.txt"),
                        ("auth_read", "cat /home/runner/.codex/auth.json >/dev/null")):
                    response = subprocess.run(["docker", "exec", server.executor_name,
                        "sh", "-c", command], capture_output=True, timeout=15)
                    checks[label] = response.returncode
            else:
                for label, command in (
                    ("workspace_write", "printf CANARY > /draft/canary.txt"),
                    ("canonical_write", "printf FORBIDDEN > /canonical/sentinel.txt"),
                    ("store_write", "printf FORBIDDEN > /store/sentinel.txt"),
                    ("auth_read", "cat /home/runner/.codex/auth.json >/dev/null")):
                    response = server.request("command/exec", {
                        "command": ["sh", "-c", command], "cwd": "/draft",
                        "timeoutMs": 15000}, timeout=25)
                    checks[label] = (response.get("result") or {}).get("exitCode")
            if self.git_workspace:
                git_check = server.request("command/exec", {
                    "command": ["git", "--version"], "cwd": "/draft",
                    "timeoutMs": 15000}, timeout=25)
                checks["git_binary"] = (git_check.get("result") or {}).get("exitCode")
                if checks["git_binary"] != 0:
                    raise RunnerError("git_image_missing_git")
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
                "image": self.image, "image_id": self.image_id,
                "cli_version": CLI_VERSION,
                "profile": self.profile,
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

    def lookup_request(self, request_id: str) -> dict:
        """Find one durable async run without starting or changing it."""
        try:
            _id(request_id)
        except (TypeError, ValueError, AttributeError):
            raise RunnerError("invalid_request_id") from None
        with self.request_lock:
            matches = []
            for record_path in (self.state / "runs").glob("*/record.json"):
                record = _read(record_path)
                if record.get("client_request_id") == request_id:
                    matches.append(record)
            if not matches:
                raise RunnerError("request_not_found")
            if len(matches) != 1:
                raise RunnerError("request_identity_conflict")
            record = matches[0]
            return {key: record.get(key) for key in
                    ("client_request_id", "request_hash", "run_id", "provider",
                     "raw_event_ref", "status")}

    def cancel(self, run_id: str) -> dict:
        with self.control_lock:
            record = self.status(run_id)
            if record["status"] == "prepared" and record.get("client_request_id"):
                record.update(status="cancelled", error_category="cancelled_before_dispatch",
                              cancel_requested=True, cancel_confirmed=True)
                _json(self._run_dir(run_id) / "record.json", record)
                return record
            if record["status"] == "running":
                flag = self.cancel_flags.get(run_id)
                if flag is None:
                    raise RunnerError("run_not_active_in_this_process")
                flag.set()
                record.update(cancel_requested=True, cancel_confirmed=False)
                _json(self._run_dir(run_id) / "record.json", record)
                return record
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
        try:
            skill_text = (target / "SKILL.md").read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            raise RunnerError("skill_frontmatter_name_required") from None
        if not skill_text.startswith("---\n") or "\n---\n" not in skill_text[4:]:
            raise RunnerError("skill_frontmatter_name_required")
        frontmatter = skill_text[4:].split("\n---\n", 1)[0]
        names = [line.split(":", 1)[1].strip().strip("\"'")
                 for line in frontmatter.splitlines() if line.startswith("name:")]
        if names != [ref["skill_id"]]:
            raise RunnerError("skill_frontmatter_name_mismatch")
        return {"skill_id": ref["skill_id"], "revision_id": ref["revision_id"],
                "tree_hash": ref["tree_hash"], "file_hashes": record["file_hashes"],
                "delivery_mode": "project_discovery", "use_evidence": "offered"}

    def _prepare(self, request: dict, *, client_request_id=None,
                 request_hash=None) -> dict:
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
        if "github_scope" in request:
            raise RunnerError("github_scope_must_come_from_authority")
        github_ref = request.get("github_authorization_ref")
        if github_ref is not None and (self.github_authority is None or
                                       not self.supervise_containers or
                                       self.split_executor or
                                       self.lease_service is None or
                                       self.mediator_state is None):
            raise RunnerError("mediated_lease_required")
        run_id = str(uuid4())
        run_dir = self._run_dir(run_id)
        run_dir.mkdir()
        workspace, canonical, store_mount = (run_dir / x for x in
                                              ("workspace", "canonical", "store"))
        try:
            try:
                github_scope = (self.github_authority.bind_run(
                    github_ref, run_id,
                    allowed_operations=frozenset(
                        {"actions_read", "pr_create", "pr_update", "pr_read"} |
                        ({"git_push"} if self.git_workspace else set())))
                                if github_ref is not None else None)
            except MediationError as error:
                raise RunnerError(error.code) from None
            if self.git_workspace:
                try:
                    baseline = prepare_git_workspace(source, workspace)
                except GitWorkspaceError as error:
                    raise RunnerError(str(error)) from error
                source_hash = _copy_tree(workspace, canonical, exclude_root_git=True)
            else:
                baseline = None
                source_hash = _copy_tree(source, workspace)
                # Preserve the tested read-only canonical and sibling store mounts.
                if _copy_tree(source, canonical) != source_hash:
                    raise RunnerError("source_changed_during_snapshot")
            store_mount.mkdir()
            (store_mount / "sentinel.txt").write_text("STORE-ORIGINAL", encoding="utf-8")
            skills = [self._materialize(workspace, ref) for ref in refs]
            artifacts = import_selected(request.get("artifact_refs", []), workspace,
                                        self._artifact_source, _hash_tree)
            effective_hash = _hash_tree(workspace, exclude_root_git=self.git_workspace)
            (run_dir / "raw-events.jsonl").touch()
            record = {"schema_version": 1, "run_id": run_id, "status": "prepared",
                      "error_category": None, "source_hash": source_hash,
                      "workspace_mode": "git" if self.git_workspace else "files",
                      "git_baseline": baseline,
                      "post_run_hash_scope": (
                          "working_files_only" if self.git_workspace else "all_files"),
                      "effective_hash": effective_hash, "post_run_hash": None,
                      "input_hash": "sha256:" + hashlib.sha256(task.encode()).hexdigest(),
                      "skill": skills[0] if len(skills) == 1 else None,
                      "skills": skills,
                      "provider": getattr(self, "provider", "codex"),
                      "handoff": handoff, "imported_artifacts": artifacts,
                      "requested_model": model, "requested_effort": effort,
                      "effective_model": None, "effective_effort": None,
                      "profile": self.profile,
                      "execution_mode": "split" if self.split_executor else "legacy",
                      "image": self.image, "image_id": self.image_id,
                      "cli_version": CLI_VERSION,
                      "config_sha256": CONFIG_SHA256, "thread_id": None,
                      "credential": ({"credential_mode": "chatgpt_plan_oauth",
                                      "credential_ref": None,
                                      "auth_outcome": "not_checked"}
                                     if self.auth else None),
                      "runner_instance_id": self.instance_id,
                      "turns": [], "answer": None, "output_ref": None,
                      "raw_event_ref": f"laomedo:run:{run_id}:events",
                      "client_request_id": client_request_id,
                      "request_hash": request_hash,
                      "cancel_requested": False, "cancel_confirmed": False}
            if github_scope is not None:
                record["github_scope"] = github_scope
            _json(run_dir / "record.json", record)
        except Exception:
            shutil.rmtree(run_dir)
            raise
        return record

    def start(self, request: dict) -> dict:
        record = self._prepare(request)
        return self._execute(record["run_id"], request["task"], resume=False)

    def start_async(self, request: dict, *, response_gate=None) -> dict:
        """Reserve one request identity, then run only after the HTTP reply."""
        if not isinstance(request, dict):
            raise RunnerError("invalid_request")
        request_id = request.get("request_id")
        try:
            _id(request_id)
        except (TypeError, ValueError, AttributeError):
            raise RunnerError("invalid_request_id") from None
        body = {key: value for key, value in request.items() if key != "request_id"}
        request_hash = "sha256:" + hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False).encode("utf-8")).hexdigest()
        with self.request_lock:
            for record_path in (self.state / "runs").glob("*/record.json"):
                prior = _read(record_path)
                if prior.get("client_request_id") == request_id:
                    if prior.get("request_hash") != request_hash:
                        raise RunnerError("request_identity_conflict")
                    return prior
            record = self._prepare(body, client_request_id=request_id,
                                   request_hash=request_hash)
            gate = response_gate or threading.Event()
            if response_gate is None:
                gate.set()
            worker = threading.Thread(target=self._async_worker,
                                      args=(record["run_id"], body["task"], gate),
                                      daemon=True)
            worker.start()
            return record

    def _async_worker(self, run_id, task, gate):
        gate.wait()
        try:
            self._execute(run_id, task, resume=False)
        except RunnerError as exc:
            with self.control_lock:
                record = self.status(run_id)
                if record["status"] == "prepared":
                    record.update(status="failed", error_category=str(exc))
                    _json(self._run_dir(run_id) / "record.json", record)

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
                record["profile"] != self.profile or
                record.get("workspace_mode", "files") != (
                    "git" if self.git_workspace else "files") or
                record.get("execution_mode", "legacy") != (
                    "split" if self.split_executor else "legacy") or
                record["image"] != self.image or
                record["image_id"] != self.image_id or
                record["cli_version"] != CLI_VERSION or
                record["config_sha256"] != CONFIG_SHA256):
            raise RunnerError("resume_binding_mismatch")
        run_dir = self._run_dir(run_id)
        snapshot = run_dir / "post-run"
        workspace = run_dir / "workspace"
        if not snapshot.exists() or _hash_tree(snapshot) != expected_post_run_hash:
            raise RunnerError("post_run_snapshot_mismatch")
        if _hash_tree(workspace, exclude_root_git=self.git_workspace) != expected_post_run_hash:
            raise RunnerError("workspace_changed_since_snapshot")
        if (_hash_tree(run_dir / "canonical") != record["source_hash"] or
                (run_dir / "store/sentinel.txt").read_text(encoding="utf-8") !=
                "STORE-ORIGINAL"):
            raise RunnerError("protected_mount_changed")
        if self.auth:
            if record.get("runner_instance_id") != self.instance_id:
                raise RunnerError("resume_after_runner_restart_forbidden")
            _token, current = self.auth.access_token()
            prior = record.get("credential") or {}
            if any(current.get(key) != prior.get(key) for key in
                   ("credential_ref", "provider_subject_hash")):
                raise RunnerError("resume_auth_identity_mismatch")
        return self._execute(run_id, task, resume=True)

    def _mediator_route(self) -> tuple[str, str]:
        # host.docker.internal -> host loopback is checked by the Windows
        # Docker Desktop probe. Other network layouts need their own check.
        if os.name != "nt" or self.mediator_state is None:
            raise RunnerError("mediator_container_route_unverified")
        try:
            status = json.loads((self.mediator_state / "mediator.json").read_text(
                encoding="utf-8"))
            port = status["port"]
            instance = status["instance"]
            if type(port) is not int or not 1 <= port <= 65535 or not re.fullmatch(
                    r"[0-9a-f]{32}", instance):
                raise ValueError("invalid_mediator_status")
            with urlopen(f"http://127.0.0.1:{port}/v1/health", timeout=2) as response:
                health = json.load(response)
            if health != {"status": "ready", "instance": instance}:
                raise ValueError("mediator_instance_mismatch")
        except (OSError, ValueError, KeyError, TypeError, TimeoutError) as error:
            raise RunnerError("mediator_unavailable") from error
        return f"http://host.docker.internal:{port}/v1/mediate", instance

    def _execute(self, run_id: str, task: str, *, resume: bool) -> dict:
        if not self.lock.acquire(blocking=False):
            raise RunnerError("runner_busy")
        run_dir, record, cancelled, server, lease = None, None, None, None, None
        launch_attempted = False
        try:
            run_dir = self._run_dir(run_id)
            with self.control_lock:
                record = self.status(run_id)
                if record["status"] == "cancelled" and record.get("cancel_confirmed"):
                    return record
                if (not resume and record["status"] != "prepared") or (
                        resume and record["status"] != "completed"):
                    raise RunnerError("run_not_dispatchable")
                cancelled = threading.Event()
                self.cancel_flags[run_id] = cancelled
                record["status"] = "running"
                name = "laomedo-codex-" + uuid4().hex
                launch_token = uuid4().hex
                record["container_ownership"] = {
                    "name": name, "launch_token": launch_token,
                    "supervised": self.supervise_containers,
                    "cleanup_verified": False}
                _json(run_dir / "record.json", record)
            if self.supervise_containers:
                if self.lease_service is None:
                    raise RunnerError("lease_service_required")
                try:
                    lease = LeaseClient(self.lease_service, run_id=run_id, name=name,
                                        token=launch_token, cancelled=cancelled,
                                        mediation_request=record.get("github_scope"))
                except (OSError, RuntimeError):
                    raise RunnerError("lease_service_unavailable") from None
                record["container_ownership"]["lease_instance"] = lease.instance
                record["container_ownership"]["grant_id"] = lease.grant_id
                with self.control_lock:
                    _json(run_dir / "record.json", record)
            capability = None
            mediator_url = None
            mediator_instance = None
            if record.get("github_scope") is not None:
                if lease is None or lease.grant_id is None:
                    raise RunnerError("mediated_grant_unavailable")
                capability = lease.dir / "grant.secret"
                if capability.is_symlink() or not capability.is_file():
                    raise RunnerError("mediated_capability_unavailable")
                mediator_url, mediator_instance = self._mediator_route()
            access_token, auth_summary = self.auth.access_token() if self.auth else (None, None)
            if resume and self.auth:
                prior = record.get("credential") or {}
                if any(auth_summary.get(key) != prior.get(key) for key in
                       ("credential_ref", "provider_subject_hash")):
                    raise RunnerError("resume_auth_identity_mismatch")
            record["credential"] = auth_summary
            _json(run_dir / "record.json", record)
            launch_attempted = True
            server = self._open_server(
                run_dir, access_token=access_token, name=name, run_id=run_id,
                launch_token=launch_token, capability=capability,
                mediator_url=mediator_url,
                mediator_instance=mediator_instance,
                repository=(record.get("github_scope") or {}).get("repository"),
                branch=(record.get("github_scope") or {}).get("branch"))
            initialized = server.request("initialize", {"clientInfo": {
                "name": "laomedo_local_runner", "title": "Laomedo Local Runner",
                "version": "0.1.0"},
                **({"capabilities": {"experimentalApi": True}}
                   if self.split_executor else {})})
            if "result" not in initialized:
                raise RunnerError("initialize_rejected")
            server.notify("initialized", {})
            if self.split_executor:
                server.register_executor()
            models = server.request("model/list", {})
            entries = (models.get("result") or {}).get("data") or []
            choice = next((x for x in entries if x.get("id") == record["requested_model"]), None)
            levels = {item.get("reasoningEffort") if isinstance(item, dict) else item
                      for item in (choice or {}).get("supportedReasoningEfforts", [])}
            if choice is None or record["requested_effort"] not in levels:
                raise RunnerError("unsupported_model_effort")
            if cancelled.is_set():
                record.update(status="cancelled", error_category="cancelled_before_turn",
                              cancel_requested=True)
                return record
            self._turn_available()
            method = "thread/resume" if resume else "thread/start"
            params = ({"threadId": record["thread_id"], "cwd": "/draft"} if resume else
                      {"model": record["requested_model"], "cwd": "/draft",
                       "approvalPolicy": "never"})
            if self.split_executor:
                params["environments"] = server.thread_environment()
                server.assert_executor_selection(params["environments"])
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
            if cancelled.is_set():
                record.update(status="cancelled", error_category="cancelled_before_turn",
                              cancel_requested=True)
                return record
            attempt = self._reserve_turn()
            record["attempt_number"] = attempt
            _json(run_dir / "record.json", record)
            if cancelled.is_set():
                record.update(status="cancelled", error_category="cancelled_before_turn",
                              cancel_requested=True)
                return record
            if record.get("github_scope") is not None:
                task += ("\n\nThis run has approved, bounded GitHub mediation "
                         "for its selected Actions reads, bound PR read/create/update, and "
                         "verified-commit branch push operations. A "
                         "bundle_freeze request only captures the fixed in-run "
                         "Git bundle; it does not verify or push it. "
                         "To request one of those operations, pipe one JSON object "
                         "with repository, operation, payload and (for a write) "
                         "effect_id to `node /run/laomedo/mediate.mjs`. "
                         "The client reads its run capability from a read-only file; "
                         "never print or copy that file. A denied or unknown write "
                         "must not be retried automatically. Direct host GitHub "
                         "credentials and ambient gh login are unavailable.")
                if self.git_workspace:
                    task += (" Native `git push origin HEAD:refs/heads/" +
                             record["github_scope"]["branch"] +
                             "` and `git fetch origin` use the mediated helper. "
                             "Fetch requires an explicitly granted read operation. "
                             "The supported `gh pr view/create/edit`, `gh run list`, "
                             "and GET-only `gh api` adapter is on PATH. "
                             "PR writes require LAOMEDO_EFFECT_ID and "
                             "LAOMEDO_RECONCILIATION_MARKER, an explicit title/body "
                             "and target; unsupported commands fail visibly. "
                             "Second pushes are not supported yet; never force or "
                             "fall back to direct HTTPS.")
            turn_params = {"threadId": native_id,
                "model": record["requested_model"], "effort": record["requested_effort"],
                "cwd": "/draft", "input": [{"type": "text", "text": task}]}
            if self.split_executor:
                server.assert_controller_isolated()
                turn_params["environments"] = server.turn_environment()
                server.assert_executor_selection(turn_params["environments"])
                turn_params["sandboxPolicy"] = {"type": "externalSandbox",
                                                 "networkAccess": "restricted"}
            if self.auth:
                auth_failure = {"error": "auth_revoked_during_turn",
                                "outcome": "revoked", "code": "auth_revoked"}

                def still_authorized():
                    try:
                        current = self.auth.active()
                        selected = self.auth.summary(current)
                    except AuthError as exc:
                        category, outcome = _auth_record_error(exc)
                        auth_failure.update(error=category + "_during_turn",
                                            outcome=outcome, code=str(exc))
                        return False
                    except (OSError, ValueError):
                        auth_failure.update(error="auth_unavailable_during_turn",
                                            outcome="unavailable",
                                            code="auth_mode_unavailable")
                        return False
                    if current.get("state") != "active":
                        if current.get("state") in {"refresh_unknown",
                                                    "refresh_in_flight"}:
                            auth_failure.update(error="auth_refresh_failed_during_turn",
                                                outcome="refresh_unknown",
                                                code="auth_refresh_unknown")
                        return False
                    if any(selected.get(key) != auth_summary.get(key)
                           for key in ("credential_ref", "provider_subject_hash")):
                        auth_failure.update(error="auth_account_changed_during_turn",
                                            outcome="account_mismatch",
                                            code="auth_account_mismatch")
                        return False
                    if selected.get("generation") != auth_summary.get("generation"):
                        auth_failure.update(error="auth_generation_changed_during_turn",
                                            outcome="generation_changed",
                                            code="auth_generation_changed")
                        return False
                    return True

                server.authorization_probe = still_authorized
                if not still_authorized():
                    raise AuthError(auth_failure["code"])
            sent = server.request("turn/start", turn_params)
            turn_id = ((sent.get("result") or {}).get("turn") or {}).get("id")
            if not turn_id:
                raise RunnerError("turn_dispatch_rejected")
            server.active_thread_id = native_id
            status, error = server.wait_turn(turn_id, 180, cancelled)
            if self.auth and error == "auth_revoked_during_turn":
                error = auth_failure["error"]
                record["credential"]["auth_outcome"] = auth_failure["outcome"]
            native_errors = _native_error_summary(server.events, turn_id)
            if status == "failed" and error is None and native_errors["last_category"]:
                error = "codex_" + native_errors["last_category"]
            record["turns"].append({"turn_id": turn_id, "status": status,
                                    "error_category": error,
                                    "native_error_summary": native_errors,
                                    "input_hash": "sha256:" +
                                    hashlib.sha256(task.encode()).hexdigest()})
            record["status"] = "completed" if status == "completed" else status
            record["error_category"] = error
            if status == "cancelled":
                record["cancel_requested"] = True
            record["native_error_summary"] = native_errors
            record["answer"] = _answer(server.events) if status == "completed" else None
            if status == "completed" and not record["answer"]:
                raise RunnerError("completed_without_agent_message")
            if status == "completed":
                post_hash = _hash_tree(run_dir / "workspace",
                                       exclude_root_git=self.git_workspace)
                pending = run_dir / ("post-run-pending-" + uuid4().hex)
                _copy_tree(run_dir / "workspace", pending,
                           exclude_root_git=self.git_workspace)
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
            if lease is not None and lease.lost.is_set():
                raise RunnerError("lease_service_lost")
        except Exception as exc:
            if record is None:
                raise
            if record["status"] not in {"interrupted", "cancelled"}:
                record["status"] = "failed"
                if isinstance(exc, AuthError):
                    category, outcome = _auth_record_error(exc)
                    record["error_category"] = category
                    if isinstance(record.get("credential"), dict):
                        record["credential"]["auth_outcome"] = outcome
                else:
                    record["error_category"] = (str(exc) if isinstance(exc, RunnerError)
                                                else type(exc).__name__)
        finally:
            close_error = False
            try:
                if server is not None:
                    server.close()
                    if record is not None and record.get("status") == "cancelled":
                        record["cancel_confirmed"] = True
            except Exception:
                close_error = True
                if record is not None:
                    record.update(status="failed", error_category="container_termination_unverified")
            finally:
                try:
                    if record is not None and self.supervise_containers and not launch_attempted:
                        verified, detail = True, "not_launched"
                        if lease is not None:
                            try:
                                lease.finish()
                            except Exception:
                                verified, detail = False, "lease_service_unverified"
                        record["container_ownership"]["cleanup_verified"] = verified
                        record["container_ownership"]["cleanup_detail"] = detail
                        if not verified:
                            record.update(status="failed",
                                          error_category="container_termination_unverified")
                    elif record is not None and self.supervise_containers:
                        verified, detail = cleanup_exact(name, run_id, launch_token)
                        if lease is not None:
                            try:
                                lease.finish()
                            except Exception:
                                verified = False
                                detail = "lease_service_unverified"
                        # A failed normal close may have been completed by the
                        # independent supervisor after its pipe closed.
                        if not verified:
                            verified, detail = cleanup_exact(name, run_id, launch_token)
                        record["container_ownership"]["cleanup_verified"] = verified
                        record["container_ownership"]["cleanup_detail"] = detail
                        if not verified:
                            record.update(status="failed",
                                          error_category="container_termination_unverified")
                    with self.control_lock:
                        if record is not None:
                            if cancelled is not None and cancelled.is_set():
                                record["cancel_requested"] = True
                            _json(run_dir / "record.json", record)
                        self.cancel_flags.pop(run_id, None)
                finally:
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

        def _authorized(self):
            supplied = self.headers.get("Authorization", "")
            if not secrets.compare_digest(supplied, "Bearer " + runner.api_token):
                self._reply(401, {"status": "failed", "error_category": "unauthorized"})
                return False
            return True

        def do_GET(self):
            if not self._authorized():
                return
            try:
                parts = self.path.strip("/").split("/")
                if len(parts) != 3:
                    raise RunnerError("unknown_endpoint")
                if parts[:2] == ["v1", "runs"]:
                    result = runner.status(parts[2])
                elif parts[:2] == ["v1", "requests"]:
                    result = runner.lookup_request(parts[2])
                else:
                    raise RunnerError("unknown_endpoint")
                self._reply(200, result)
            except (RunnerError, ValueError, OSError) as exc:
                category = str(exc)
                code = (409 if category == "request_identity_conflict" else
                        400 if category == "invalid_request_id" else 404)
                self._reply(code, {"status": "failed", "error_category": category})

        def do_POST(self):
            if not self._authorized():
                return
            response_gate = None
            try:
                parts = self.path.strip("/").split("/")
                body = self._body()
                is_cancel_endpoint = (len(parts) == 4 and parts[:2] == ["v1", "runs"]
                                      and parts[3] == "cancel")
                if parts == ["v1", "runs", "async"]:
                    response_gate = threading.Event()
                    result = runner.start_async(body, response_gate=response_gate)
                    self._reply(202, result)
                    return
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
                code = (202 if is_cancel_endpoint and result.get("cancel_requested") and
                        not result.get("cancel_confirmed") else
                        200 if result["status"] == "completed" or
                        (is_cancel_endpoint and result["status"] == "cancelled") else 502)
                self._reply(code, result)
            except (RunnerError, SkillStoreError, ArtifactError, KeyError, ValueError, OSError) as exc:
                self._reply(409 if str(exc) == "request_identity_conflict" else 400,
                            {"status": "failed", "error_category": str(exc)})
            finally:
                if response_gate is not None:
                    response_gate.set()

    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--skill-store", type=Path, required=True)
    parser.add_argument("--source-workspace", type=Path, required=True)
    parser.add_argument("--git-workspace", action="store_true",
                        help="Opt-in isolated Git checkout; mediated push remains disabled")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--max-model-turns", type=int, default=0)
    parser.add_argument("--lease-service", type=Path,
                        help="State directory of an independently started lease service")
    parser.add_argument("--github-authority-store", type=Path,
                        help="Trusted run-approval database outside the checkout")
    parser.add_argument("--mediator-state", type=Path,
                        help="Private host mediator state; only its port is passed to Docker")
    parser.add_argument("--split-executor", action="store_true",
                        help="Credential-free experimental split controller/executor")
    parser.add_argument("--auth-store", type=Path,
                        help="Private app-owned ChatGPT OAuth store; requires --split-executor")
    args = parser.parse_args()
    if (args.github_authority_store is None) != (args.mediator_state is None):
        parser.error("GitHub authority and mediator state must be configured together")
    authority = (RunGrantAuthority(args.github_authority_store)
                 if args.github_authority_store else None)
    runner = LocalRunner(args.state, args.skill_store, args.source_workspace,
                         git_workspace=args.git_workspace,
                         max_model_turns=args.max_model_turns,
                         lease_service=args.lease_service,
                         github_authority=authority,
                         mediator_state=args.mediator_state,
                         split_executor=args.split_executor,
                         auth_store=args.auth_store)
    if args.preflight:
        print(json.dumps(runner.preflight(), indent=2))
        return
    serve(runner, port=args.port).serve_forever()


if __name__ == "__main__":
    main()
