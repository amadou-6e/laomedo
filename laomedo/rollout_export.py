"""Copy one native Codex rollout from the existing private volume for AGENTVIZ."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
from uuid import UUID, uuid4

from .local_runner import IMAGE, VOLUME, RunnerError, _id, _private, _read


SESSIONS = PurePosixPath("/home/runner/.codex/sessions")


def export_rollout(state: Path, run_id: str, *, docker_run=subprocess.run) -> Path:
    run_dir = _private(state) / "runs" / _id(run_id)
    record = _read(run_dir / "record.json")
    thread_id = record.get("thread_id")
    try:
        if str(UUID(thread_id)) != thread_id:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise RunnerError("invalid_native_thread_id") from None
    prefix = ["docker", "run", "--rm", "--pull=never", "--user", "10001:10001",
              "--mount", f"type=volume,source={VOLUME},target=/home/runner/.codex,readonly",
              IMAGE]
    listing = docker_run([*prefix, "find", str(SESSIONS), "-type", "f", "-links", "1",
                          "-name", f"*{thread_id}*.jsonl"], capture_output=True,
                         check=True, timeout=30)
    paths = listing.stdout.decode("utf-8").splitlines()
    if len(paths) != 1:
        raise RunnerError("native_rollout_not_unique")
    path = PurePosixPath(paths[0])
    if not path.is_relative_to(SESSIONS) or ".." in path.parts:
        raise RunnerError("native_rollout_path_invalid")
    size_raw = docker_run([*prefix, "stat", "-c", "%s", str(path)],
                          capture_output=True, check=True, timeout=30).stdout
    try:
        size = int(size_raw.strip())
    except ValueError:
        raise RunnerError("native_rollout_size_invalid") from None
    if not 0 < size <= 64 * 1024 * 1024:
        raise RunnerError("native_rollout_size_invalid")
    content = docker_run([*prefix, "cat", str(path)], capture_output=True,
                         check=True, timeout=30).stdout
    if len(content) != size:
        raise RunnerError("native_rollout_size_invalid")
    lines = content.splitlines()
    for line in lines:
        json.loads(line)
    first = json.loads(lines[0])
    if (first.get("type") != "session_meta" or
            (first.get("payload") or {}).get("id") != thread_id):
        raise RunnerError("native_rollout_identity_mismatch")
    output = run_dir / "native-rollout.jsonl"
    pending = run_dir / ("native-rollout.pending-" + uuid4().hex)
    pending.write_bytes(content)
    os.replace(pending, output)
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    output = export_rollout(args.state, args.run_id)
    print("native_rollout_ref=" + f"laomedo:run:{args.run_id}:native-rollout")
    print("private_file_written=true")
    print("bytes=" + str(output.stat().st_size))


if __name__ == "__main__":
    main()
