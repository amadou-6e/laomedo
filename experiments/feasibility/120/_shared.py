"""Shared app-server client and utilities for Codex probes (issue 120).

Fixes over the first probe draft:
- Buffers notifications and server requests instead of dropping them.
- Uses a monotonic request-id counter (no id collisions).
- Raises a typed RequestTimeout instead of an uncaught queue.Empty.
- Accepts both API-key and (rejected) ChatGPT auth modes for the gate.
- Records the real Codex version.

No protocol behavior is assumed beyond the documented app-server reference.
"""

import hashlib
import json
import os
import queue
from pathlib import Path
import subprocess
import threading
import time


DEFAULT_TIMEOUT = 20.0


class RequestTimeout(TimeoutError):
    """Raised when no matching response arrives before the deadline."""


def fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    if not root.exists():
        return "absent"
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        if path.is_file():
            with path.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    digest.update(chunk)
    return digest.hexdigest()


def hash_path(path: Path) -> str:
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    return fingerprint(path)


def personal_roots():
    personal = Path.home()
    return [
        personal / ".agents" / "skills",
        personal / ".codex" / "skills",
        personal / ".codex" / "sessions",
        personal / ".codex" / "auth.json",
    ]


def hash_personal_roots():
    return [hash_path(root) for root in personal_roots()]


def personal_root_names():
    return [
        "_".join(root.parts[-2:]) if len(root.parts) > 1 else root.name
        for root in personal_roots()
    ]


def compare_personal_roots(before, after):
    return dict(zip(personal_root_names(), (a == b for a, b in zip(before, after))))


def write_skill(root: Path, name: str, content: str = None) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    if content is None:
        content = (
            f"---\nname: {name}\ndescription: Synthetic fixture.\n---\n\n"
            "This fixture is synthetic probe content.\n"
        )
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


def ensure_clean(path: Path) -> int:
    """(Re)create a run directory, removing stale contents from a prior run.
    Returns the number of entries that could not be removed, for example a
    file locked by Windows."""
    leftover = 0
    if path.exists():
        for child in sorted(path.rglob("*"), reverse=True):
            try:
                if child.is_dir() and not child.is_symlink():
                    child.rmdir()
                else:
                    child.unlink()
            except OSError:
                leftover += 1
        leftover += len(list(path.rglob("*")))
    path.mkdir(parents=True, exist_ok=True)
    return leftover


def inside_git_tree(path: Path) -> bool:
    """True if the path is inside a git working tree (including .git dirs)."""
    for candidate in [path.resolve(), *path.resolve().parents]:
        if (candidate / ".git").exists():
            return True
    return False


def construct_env(private_home: Path, codex_home: Path, state: Path, codex_parent: Path):
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    return {
        "HOME": str(private_home),
        "USERPROFILE": str(private_home),
        "HOMEDRIVE": private_home.drive,
        "HOMEPATH": str(private_home)[len(private_home.drive):],
        "CODEX_HOME": str(codex_home),
        "APPDATA": str(state / "appdata"),
        "LOCALAPPDATA": str(state / "localappdata"),
        "TEMP": str(state),
        "TMP": str(state),
        "SystemRoot": system_root,
        "WINDIR": system_root,
        "PATH": os.pathsep.join([str(codex_parent), str(Path(system_root) / "System32")]),
    }


def login_status(codex: Path, cwd: Path, env: dict) -> dict:
    """Report the auth mode without printing credential material."""
    try:
        result = subprocess.run(
            [str(codex), "login", "status"], cwd=cwd, env=env,
            capture_output=True, text=True, timeout=20, encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": type(exc).__name__}
    text = (result.stdout + result.stderr).lower()
    return {
        "ok": result.returncode == 0,
        "exit_code": result.returncode,
        "chatgpt": result.returncode == 0 and "chatgpt" in text,
        "api_key": result.returncode == 0 and "api key" in text,
    }


def resettable_dir(root: Path) -> tuple:
    """A run directory safe to reset, with a guard against deleting anything
    outside the experiment tree. Returns (resolved_path, leftover_count)."""
    experiment = Path(__file__).resolve().parent
    resolved = root.resolve()
    if not resolved.is_relative_to(experiment):
        raise ValueError("refusing to reset a directory outside the experiment tree")
    leftovers = ensure_clean(resolved)
    return resolved, leftovers


def credential_gate(codex: Path, cwd: Path, env: dict, codex_home: Path,
                    state: Path, api_host: str = "api.openai.com",
                    api_port: int = 443) -> dict:
    """Decide whether a model call is permitted.

    Accepts a dedicated API-key credential. Rejects a copied personal ChatGPT
    login, missing auth, an unknown auth mode, a state dir inside a git tree,
    and unreachable connectivity. No credential value is read or printed.
    """
    verdict = {"permitted": False}
    if inside_git_tree(state):
        verdict["reason"] = "state_dir_inside_git_tree"
        return verdict
    if not (codex_home / "auth.json").is_file():
        verdict["reason"] = "missing_auth_file"
        return verdict
    status = login_status(codex, cwd, env)
    verdict["login_status"] = status
    if not status.get("ok"):
        verdict["reason"] = "login_status_failed"
        return verdict
    if status.get("chatgpt"):
        verdict["reason"] = "personal_chatgpt_login_not_allowed"
        return verdict
    if not status.get("api_key"):
        verdict["reason"] = "unknown_auth_mode"
        return verdict
    verdict["credential_mode"] = "api_key"
    host = verdict["api_host"] = api_host
    port = verdict["api_port"] = api_port
    if not tcp_reachable(host, port):
        verdict["reason"] = "api_host_unreachable"
        return verdict
    verdict["permitted"] = True
    return verdict


def tcp_reachable(host: str, port: int, timeout: float = 3.0) -> bool:
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def codex_version(codex: Path, env: dict) -> str:
    try:
        result = subprocess.run(
            [str(codex), "--version"], env=env, capture_output=True, text=True,
            timeout=20, encoding="utf-8", errors="replace",
        )
        return (result.stdout + result.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return f"unavailable: {type(exc).__name__}"


class AppServer:
    """One app-server connection that never drops messages.

    All messages that are not the response to the current request are kept in
    self.events in arrival order: notifications (method, no id) and
    server-initiated requests (method and id).
    """

    def __init__(self, codex: Path, cwd: Path, env: dict, state: Path):
        self.state = state
        self.error_log_path = state / "app-server.stderr.log"
        self.error_log = self.error_log_path.open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            [str(codex), "app-server", "--stdio"], cwd=cwd, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.error_log,
            text=True, encoding="utf-8",
        )
        self.messages: queue.Queue = queue.Queue()
        self.events = []
        self.invalid_lines = 0
        self._id = 1000
        threading.Thread(target=self._reader, args=(self.process.stdout,), daemon=True).start()

    def _reader(self, stream):
        for line in stream:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                self.invalid_lines += 1
                continue
            self.messages.put(message)

    def send(self, method: str, params=None, timeout: float = DEFAULT_TIMEOUT) -> dict:
        self._id += 1
        request_id = self._id
        payload = {"method": method, "id": request_id}
        if params is not None:
            payload["params"] = params
        self.process.stdin.write(json.dumps(payload) + "\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RequestTimeout(method)
            try:
                message = self.messages.get(timeout=remaining)
            except queue.Empty:
                raise RequestTimeout(method)
            if message.get("id") == request_id and "method" not in message:
                return message
            # Anything else is a notification or a server request. Keep it.
            self.events.append(message)

    def notify(self, method: str, params=None) -> None:
        payload = {"method": method}
        if params is not None:
            payload["params"] = params
        self.process.stdin.write(json.dumps(payload) + "\n")
        self.process.stdin.flush()

    def drain(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            try:
                self.events.append(self.messages.get(timeout=remaining))
            except queue.Empty:
                return

    def close(self) -> dict:
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.error_log.close()
        text = self.error_log_path.read_text(encoding="utf-8", errors="replace").lower()
        return {
            "authentication": any(x in text for x in ("auth", "unauthorized", "token expired")),
            "network": any(x in text for x in ("connection", "network", "dns", "timeout")),
            "sandbox": "sandbox" in text,
            "nonempty": bool(text.strip()),
        }

    def initialize(self) -> tuple:
        response = self.send("initialize", {
            "clientInfo": {"name": "laomedo_feasibility_120",
                           "title": "Laomedo Feasibility Probe 120",
                           "version": "0.1.0"},
        })
        ok = "result" in response
        info = response.get("result", {}) if ok else response.get("error", {})
        if ok:
            self.notify("initialized", {})
        return ok, info


def messages_of(server: AppServer, methods=()):
    """Return buffered notifications, optionally filtered by method."""
    if not methods:
        return list(server.events)
    wanted = set(methods)
    return [m for m in server.events if m.get("method") in wanted]


def summarize_methods(server: AppServer) -> dict:
    counts = {}
    for message in server.events:
        method = message.get("method")
        if method:
            counts[method] = counts.get(method, 0) + 1
    return counts
