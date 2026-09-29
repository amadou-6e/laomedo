"""Shared utilities for Codex app-server probes.

Use this module instead of probe_codex_discovery and probe_codex_skill_turn
so the #119 probes remain exact reproduction sources and this module can be
changed for #120 without affecting those reproductions.
"""

import hashlib
import json
import os
import queue
from pathlib import Path
import subprocess
import threading
import time


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


def hash_path(path):
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    return fingerprint(path)


def read_lines(stream, messages: queue.Queue, label: str = "") -> None:
    for line in stream:
        try:
            messages.put(json.loads(line))
        except json.JSONDecodeError:
            messages.put({"invalid_json": True, "label": label})


def request(process, messages: queue.Queue, payload: dict,
            timeout: float = 20) -> dict:
    process.stdin.write(json.dumps(payload) + "\n")
    process.stdin.flush()
    while True:
        message = messages.get(timeout=timeout)
        if message.get("id") == payload["id"]:
            return message


def write_skill(root: Path, name: str, content: str = None) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    if content is None:
        content = (
            f"---\nname: {name}\ndescription: Synthetic fixture.\n---\n\n"
            "This fixture must not run a model turn unless explicitly requested.\n"
        )
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


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


def construct_env(private_home, codex_home, state, codex_parent):
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


def start_app_server(codex: Path, cwd: Path, env: dict):
    error_log = (Path(env["TEMP"]) / "app-server.stderr.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [str(codex), "app-server", "--stdio"],
        cwd=cwd, env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=error_log,
        text=True, encoding="utf-8",
    )
    messages = queue.Queue()
    threading.Thread(target=read_lines, args=(process.stdout, messages), daemon=True).start()
    return process, messages, error_log


def stop_app_server(process, error_log, state):
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    error_log.close()
    error_text = (state / "app-server.stderr.log").read_text(encoding="utf-8", errors="replace").lower()
    return {
        "authentication": any(x in error_text for x in ("auth", "unauthorized", "token expired")),
        "network": any(x in error_text for x in ("connection", "network", "dns", "timeout")),
        "sandbox": "sandbox" in error_text,
        "nonempty": bool(error_text.strip()),
    }


def initialize(process, messages):
    init = request(process, messages, {
        "method": "initialize", "id": 1,
        "params": {"clientInfo": {"name": "laomedo_feasibility_120",
                                   "title": "Laomedo Feasibility Probe 120",
                                   "version": "0.1.0"}},
    })
    ok = "result" in init
    if not ok:
        return False, init
    process.stdin.write(json.dumps({"method": "initialized", "params": {}}) + "\n")
    process.stdin.flush()
    return True, init


def list_skills(process, messages, project: Path):
    found = request(process, messages, {
        "method": "skills/list", "id": 2,
        "params": {"cwds": [str(project)], "forceReload": True},
    })
    skills = found.get("result", {}).get("data", [{}])[0].get("skills", [])
    return skills


def list_models(process, messages):
    result = request(process, messages, {"method": "model/list", "id": 3, "params": {"limit": 100}})
    data = result.get("result", {}).get("data", [])
    return result, data


def start_thread(process, messages, model, cwd, effort="low", sandbox="read-only",
                 approval="never", timeout=30):
    return request(process, messages, {
        "method": "thread/start", "id": 4,
        "params": {
            "model": model, "cwd": str(cwd),
            "approvalPolicy": approval,
            "config": {"model_reasoning_effort": effort},
            "sandbox": sandbox,
        },
    }, timeout=timeout)


def start_turn(process, messages, thread_id, input_items, timeout=30):
    return request(process, messages, {
        "method": "turn/start", "id": 5,
        "params": {"threadId": thread_id, "input": input_items},
    }, timeout=timeout)
