"""Hash bundled native system skills at image build time, without authentication."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading


def response(process, request):
    """Exchange one fixed discovery request; never submit a model prompt."""
    process.stdin.write(json.dumps(request) + "\n")
    process.stdin.flush()
    for line in process.stdout:
        value = json.loads(line)
        if value.get("id") == request["id"]:
            if "error" in value:
                raise RuntimeError("native_skill_discovery_failed")
            return value["result"]
    raise RuntimeError("native_skill_discovery_unavailable")


def main():
    process = subprocess.Popen(
        ["codex", "app-server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    timer = threading.Timer(30, process.kill)
    timer.start()
    try:
        response(
            process,
            {
                "id": 1,
                "method": "initialize",
                "params": {
                    "clientInfo": {"name": "laomedo-image-skills", "version": "1"},
                },
            },
        )
        result = response(
            process,
            {
                "id": 2,
                "method": "skills/list",
                "params": {
                    "cwds": ["/draft"],
                    "forceReload": True,
                },
            },
        )
        root = Path.home() / ".codex/skills/.system"
        manifest = {}
        for entry in result["data"]:
            if entry.get("errors"):
                raise RuntimeError("native_skill_discovery_failed")
            for skill in entry["skills"]:
                if skill["scope"] != "system" or not skill["enabled"]:
                    raise RuntimeError("non_system_skill_in_clean_image")
                name = skill["name"]
                source = root / name
                if Path(skill["path"]) != source / "SKILL.md" or name in manifest:
                    raise RuntimeError("ambiguous_native_skill_source")
                files = {}
                for path in sorted(source.rglob("*")):
                    if path.is_symlink():
                        raise RuntimeError("native_skill_symlink")
                    if path.is_file():
                        files[path.relative_to(source).as_posix()] = hashlib.sha256(
                            path.read_bytes()
                        ).hexdigest()
                if "SKILL.md" not in files:
                    raise RuntimeError("native_skill_body_missing")
                manifest[name] = files
        if not manifest:
            raise RuntimeError("native_system_skills_missing")
        Path(sys.argv[1]).write_text(
            json.dumps(manifest, sort_keys=True), encoding="utf-8"
        )
    finally:
        timer.cancel()
        process.terminate()
        process.wait(timeout=10)


if __name__ == "__main__":
    main()
