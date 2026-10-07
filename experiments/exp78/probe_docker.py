"""Zero-turn skill listing inside the pinned, credential-free Codex image."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading
import time
import uuid


NAME = "fixture-native-78"
BODY = ("---\nname: fixture-native-78\n"
        "description: Synthetic skill for a credential-free discovery check.\n"
        "---\n\nPrivate fixture body; no model turn reads this text.\n")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def request(proc, inbox, method, params, request_id):
    proc.stdin.write(json.dumps({"id": request_id, "method": method,
                                 "params": params}) + "\n")
    proc.stdin.flush()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            message = inbox.get(timeout=max(0.01, deadline - time.monotonic()))
        except queue.Empty:
            break
        if message.get("id") == request_id and "method" not in message:
            return message
    raise TimeoutError(method)


def run(docker: Path, image: str) -> dict:
    result = {"issue": 78, "selection_mode": "native_listing_only",
              "model_turns": 0, "image_id": image, "skill_body_read": "unknown"}
    version = subprocess.run(
        [str(docker), "run", "--rm", "--pull", "never", "--network", "none",
         "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
         "--user", "1000:1000", "--entrypoint", "/usr/local/bin/codex",
         image, "--version"], capture_output=True, text=True, timeout=20)
    result["codex_version"] = (version.stdout.strip().splitlines() or [None])[0]
    result["version_probe_ok"] = version.returncode == 0
    container = "laomedo-exp78-" + uuid.uuid4().hex[:12]
    with tempfile.TemporaryDirectory(prefix="laomedo-exp78-image-") as temp:
        state = Path(temp).resolve()
        source = state / "source" / NAME / "SKILL.md"
        effective = state / "project" / ".agents" / "skills" / NAME / "SKILL.md"
        source.parent.mkdir(parents=True)
        effective.parent.mkdir(parents=True)
        source.write_text(BODY, encoding="utf-8")
        shutil.copyfile(source, effective)
        result["source_sha256"] = digest(source)
        result["effective_before_sha256"] = digest(effective)
        command = [str(docker), "run", "--rm", "--pull", "never", "-i",
                   "--name", container, "--network", "none", "--read-only",
                   "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                   "--user", "1000:1000", "--pids-limit", "64",
                   "--tmpfs", "/tmp:rw,nosuid,nodev,size=32m",
                   "--mount", f"type=bind,src={state / 'project'},dst=/workspace,readonly",
                   "--workdir", "/workspace", "--env", "HOME=/tmp/privatehome",
                   "--env", "CODEX_HOME=/tmp/codex-home",
                   "--env", "XDG_CONFIG_HOME=/tmp/privatehome/.config",
                   "--entrypoint", "/bin/sh", image, "-c",
                   "mkdir -p /tmp/privatehome /tmp/codex-home; exec codex app-server --stdio"]
        inbox = queue.Queue()
        proc = None
        stderr_lines = []
        try:
            proc = subprocess.Popen(command, stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, encoding="utf-8", errors="replace")

            def collect_stdout():
                for line in proc.stdout:
                    try:
                        inbox.put(json.loads(line))
                    except json.JSONDecodeError:
                        continue

            def collect_stderr():
                for line in proc.stderr:
                    stderr_lines.append(line)

            output_reader = threading.Thread(target=collect_stdout, daemon=True)
            error_reader = threading.Thread(target=collect_stderr, daemon=True)
            output_reader.start()
            error_reader.start()
            initialized = request(proc, inbox, "initialize", {
                "clientInfo": {"name": "laomedo_exp78", "title": "Laomedo EXP-78",
                               "version": "0.1.0"}}, 1001)
            result["initialized"] = "result" in initialized
            if not result["initialized"]:
                result["error_category"] = "initialize_rejected"
            else:
                proc.stdin.write(json.dumps({"method": "initialized", "params": {}}) + "\n")
                proc.stdin.flush()
                response = request(proc, inbox, "skills/list", {
                    "cwds": ["/workspace"], "forceReload": True}, 1002)
                if "result" not in response:
                    result["error_category"] = "skills_list_rejected"
                else:
                    batches = response["result"].get("data") or []
                    skills = batches[0].get("skills") or [] if batches else []
                    matches = [item for item in skills if item.get("name") == NAME]
                    expected = f"/workspace/.agents/skills/{NAME}/SKILL.md"
                    result["fixture_listing_count"] = len(matches)
                    result["fixture_path_matches_effective"] = (
                        len(matches) == 1 and matches[0].get("path") == expected)
                    classes = {"private_project": 0, "private_codex_home": 0,
                               "private_home": 0, "other": 0}
                    for item in skills:
                        path = item.get("path") or ""
                        group = ("private_project" if path.startswith("/workspace/")
                                 else "private_codex_home" if path.startswith("/tmp/codex-home/")
                                 else "private_home" if path.startswith("/tmp/privatehome/")
                                 else "other")
                        classes[group] += 1
                    result["listed_path_classes"] = classes
                    result["native_listing_event"] = {
                        "method": "skills/list",
                        "request": {"cwd_class": "private_project", "forceReload": True},
                        "response": {"skill_count": len(skills),
                                     "fixture_name": NAME if len(matches) == 1 else None,
                                     "fixture_path_class": "private_project"
                                     if result["fixture_path_matches_effective"] else "other"}}
                    result["fixture_offered"] = result["fixture_path_matches_effective"]
        except Exception as error:
            result["error_category"] = type(error).__name__
        finally:
            if proc is not None:
                if proc.stdin:
                    proc.stdin.close()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    subprocess.run([str(docker), "rm", "-f", container],
                                   capture_output=True, timeout=15)
                    proc.wait(timeout=8)
                result["container_exit_code"] = proc.returncode
                result["stderr_nonempty"] = bool("".join(stderr_lines).strip())
            inspect = subprocess.run([str(docker), "ps", "-a", "--filter",
                                      f"name=^{container}$", "--format", "{{.ID}}"],
                                     capture_output=True, text=True, timeout=15)
            result["container_removed"] = inspect.returncode == 0 and not inspect.stdout.strip()
            result["effective_after_sha256"] = digest(effective)
    result["effective_unchanged"] = (
        result["source_sha256"] == result["effective_before_sha256"] ==
        result["effective_after_sha256"])
    classes = result.get("listed_path_classes") or {}
    result["pass"] = (result["version_probe_ok"] and
                      result.get("fixture_offered") is True and
                      classes.get("other") == 0 and result["effective_unchanged"] and
                      result["container_removed"])
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--docker", required=True, type=Path)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = run(args.docker.resolve(strict=True), args.image_id)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8", newline="\n")
    print(json.dumps({"pass": result["pass"], "error_category": result.get("error_category"),
                      "fixture_offered": result.get("fixture_offered"),
                      "container_removed": result.get("container_removed")}))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
