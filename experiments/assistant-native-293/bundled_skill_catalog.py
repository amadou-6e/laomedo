"""Inspect Codex's bundled skill metadata in a credential-free disposable image."""

import json
import subprocess


def main():
    process = subprocess.Popen(
        ["codex", "app-server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        for request in (
            {
                "id": 1,
                "method": "initialize",
                "params": {
                    "clientInfo": {"name": "bundled-skill-inspection", "version": "1"}
                },
            },
            {
                "id": 2,
                "method": "skills/list",
                "params": {"cwds": ["/draft"], "forceReload": True},
            },
        ):
            process.stdin.write(json.dumps(request) + "\n")
            process.stdin.flush()
            for line in process.stdout:
                value = json.loads(line)
                if value.get("id") != request["id"]:
                    continue
                if request["id"] == 2:
                    print(json.dumps(value))
                break
    finally:
        process.terminate()
        process.wait(timeout=10)


if __name__ == "__main__":
    main()
