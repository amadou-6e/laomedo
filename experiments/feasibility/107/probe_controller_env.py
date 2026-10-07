"""Credential-free Codex controller-to-command boundary probe for #107.

Runs a disposable app-server with an internally generated canary. The real
Codex login volume is replaced by tmpfs. No model turn or browser login runs.
Only boolean observations are printed; raw app-server output stays in a
temporary directory and is removed when the probe exits.
"""

import json
from pathlib import Path
import secrets
import tempfile

from laomedo.local_runner import AppServer, VOLUME, _docker_prefix


def probe():
    canary = "LAOMEDO_107_" + secrets.token_hex(24)
    with tempfile.TemporaryDirectory(prefix="laomedo-107-") as directory:
        root = Path(directory)
        for name in ("workspace", "canonical", "store"):
            (root / name).mkdir()
        prefix = _docker_prefix(root / "workspace", root / "canonical", root / "store")
        mount = f"type=volume,source={VOLUME},target=/home/runner/.codex"
        if mount not in prefix:
            raise RuntimeError("expected_login_volume_mount_missing")
        index = prefix.index(mount)
        if index == 0 or prefix[index - 1] != "--mount":
            raise RuntimeError("unexpected_login_volume_mount_shape")
        del prefix[index - 1:index + 1]
        image_index = prefix.index("--workdir")
        prefix[image_index:image_index] = [
            "--tmpfs", "/home/runner/.codex:rw,uid=10001,gid=10001,mode=0700",
            "--env", "ACCESS_TOKEN=" + canary,
        ]
        server = AppServer(["docker", *prefix], root)
        try:
            response = server.request("initialize", {"clientInfo": {
                "name": "laomedo_107_probe", "title": "Laomedo 107 Probe",
                "version": "0.1.0"}}, timeout=30)
            if "result" not in response:
                raise RuntimeError("initialize_rejected")
            server.notify("initialized", {})
            checks = {
                "tool_environment": 'test -n "${ACCESS_TOKEN+x}"',
                "controller_proc":
                    "tr '\\000' '\\n' </proc/1/environ | grep -q '^ACCESS_TOKEN='",
                "tool_proc":
                    "tr '\\000' '\\n' </proc/self/environ | grep -q '^ACCESS_TOKEN='",
            }
            observations = {}
            for name, command in checks.items():
                reply = server.request("command/exec", {
                    "command": ["sh", "-c", command], "cwd": "/draft",
                    "timeoutMs": 15000}, timeout=25)
                exit_code = (reply.get("result") or {}).get("exitCode")
                observations[name] = {
                    "readable": exit_code == 0,
                    "exit_code": exit_code,
                }
            return {"schema_version": 1, "model_turns": 0,
                    "used_real_login_volume": False,
                    "controller_env_credential_route_safe": all(
                        not item["readable"] and item["exit_code"] is not None
                        for item in observations.values()),
                    "observations": observations}
        finally:
            server.close()


if __name__ == "__main__":
    print(json.dumps(probe(), indent=2, sort_keys=True))
