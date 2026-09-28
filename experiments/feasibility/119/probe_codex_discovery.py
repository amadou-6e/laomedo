"""Probe Codex skill discovery without authentication or model turns.

The probe creates disposable profiles and a synthetic project in a temporary
directory. It prints only fixture names, counts, and profile comparison results.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import tempfile
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


def write_skill(root: Path, name: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Synthetic discovery fixture.\n---\n\n"
        "This fixture must not run a model turn.\n",
        encoding="utf-8",
    )


def read_lines(stream, messages: queue.Queue) -> None:
    for line in stream:
        try:
            messages.put(json.loads(line))
        except json.JSONDecodeError:
            messages.put({"invalid_json": True})


def request(process, messages: queue.Queue, payload: dict, timeout: int = 20) -> dict:
    process.stdin.write(json.dumps(payload) + "\n")
    process.stdin.flush()
    while True:
        message = messages.get(timeout=timeout)
        if message.get("id") == payload["id"]:
            if "error" in message:
                raise RuntimeError(f"app-server error code: {message['error'].get('code')}")
            return message.get("result", {})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", type=Path, required=True)
    args = parser.parse_args()
    codex = args.codex.resolve(strict=True)
    real_home = Path.home()
    personal_roots = [
        real_home / ".agents" / "skills",
        real_home / ".codex" / "skills",
        real_home / ".codex" / "sessions",
    ]
    before = [fingerprint(root) for root in personal_roots]

    # On Windows, a just-terminated app-server child can briefly retain a
    # directory handle. Do not let that cleanup race hide the probe result.
    with tempfile.TemporaryDirectory(prefix="laomedo-119-", ignore_cleanup_errors=True) as temporary:
        scratch = Path(temporary)
        home = scratch / "home"
        codex_home = scratch / "codex-home"
        project = scratch / "project"
        home.mkdir()
        codex_home.mkdir()
        project.mkdir()
        write_skill(home / ".agents" / "skills", "fixture-user")
        write_skill(project / ".agents" / "skills", "fixture-repo")
        write_skill(codex_home / "skills", "fixture-codex-home")

        # This is a constructed environment, not a copy of os.environ.
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        environment = {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "HOMEDRIVE": home.drive,
            "HOMEPATH": str(home)[len(home.drive) :],
            "CODEX_HOME": str(codex_home),
            "APPDATA": str(scratch / "appdata"),
            "LOCALAPPDATA": str(scratch / "localappdata"),
            "TEMP": str(scratch),
            "TMP": str(scratch),
            "SystemRoot": system_root,
            "WINDIR": system_root,
            "PATH": os.pathsep.join([str(codex.parent), str(Path(system_root) / "System32")]),
        }
        process = subprocess.Popen(
            [str(codex), "app-server", "--stdio"],
            cwd=project,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
        )
        messages: queue.Queue = queue.Queue()
        reader = threading.Thread(target=read_lines, args=(process.stdout, messages), daemon=True)
        reader.start()
        try:
            request(
                process,
                messages,
                {
                    "method": "initialize",
                    "id": 1,
                    "params": {
                        "clientInfo": {
                            "name": "laomedo_feasibility",
                            "title": "Laomedo Feasibility Probe",
                            "version": "0.1.0",
                        }
                    },
                },
            )
            process.stdin.write(json.dumps({"method": "initialized", "params": {}}) + "\n")
            process.stdin.flush()
            result = request(
                process,
                messages,
                {"method": "skills/list", "id": 2, "params": {"cwds": [str(project)], "forceReload": True}},
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            time.sleep(0.5)

    after = [fingerprint(root) for root in personal_roots]
    skills = result.get("data", [{}])[0].get("skills", [])
    names = {skill.get("name") for skill in skills}
    real_home_resolved = real_home.resolve()
    scratch_resolved = scratch.resolve()
    personal_skill_count = 0
    scratch_skill_count = 0
    for skill in skills:
        path_text = skill.get("path")
        if not path_text:
            continue
        skill_path = Path(path_text).resolve()
        if skill_path.is_relative_to(scratch_resolved):
            scratch_skill_count += 1
        elif skill_path.is_relative_to(real_home_resolved):
            personal_skill_count += 1
    print(
        json.dumps(
            {
                "fixture_repo_discovered": "fixture-repo" in names,
                "fixture_user_discovered": "fixture-user" in names,
                "fixture_codex_home_discovered": "fixture-codex-home" in names,
                "other_skill_count": len(names - {"fixture-repo", "fixture-user", "fixture-codex-home"}),
                "personal_skill_count": personal_skill_count,
                "scratch_skill_count": scratch_skill_count,
                "personal_roots_unchanged": {
                    "user_skills": before[0] == after[0],
                    "codex_skills": before[1] == after[1],
                    "codex_sessions": before[2] == after[2],
                },
                "model_calls": 0,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
