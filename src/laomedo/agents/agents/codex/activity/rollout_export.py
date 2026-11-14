"""Copy one native Codex rollout from the existing private volume for AGENTVIZ."""

from __future__ import annotations
from laomedo.docker import DockerRuntime

from pathlib import Path
from pathlib import PurePosixPath
from uuid import UUID
from uuid import uuid4
import argparse
import json
from laomedo.agents.errors import RunnerError
from laomedo.agents.agents.base.utils import _id
from laomedo.agents.agents.base.utils import _private
from laomedo.agents.agents.base.utils import _read
import os
import re

SESSIONS = PurePosixPath("/home/runner/.codex/sessions")


def export_rollout(state: Path, run_id: str) -> Path:
    """Export exact retained history using only the run's recorded Docker binding."""
    run_dir = _private(state) / "runs" / _id(run_id)
    record = _read(run_dir / "record.json")
    thread_id = record.get("thread_id")
    try:
        if str(UUID(thread_id)) != thread_id:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise RunnerError("invalid_native_thread_id") from None
    owner = record.get("container_ownership")
    endpoint = owner.get("docker_endpoint") if isinstance(owner, dict) else None
    profile, image = record.get("profile"), record.get("image_id")
    if (
        not isinstance(endpoint, str)
        or not endpoint.strip()
        or not isinstance(profile, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]+", profile)
        or not isinstance(image, str)
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", image)
    ):
        raise RunnerError("native_rollout_binding_invalid")

    from py_docker.errors import CleanupUnconfirmedError, DockerOperationError

    receipts = run_dir / "rollout-receipts"
    receipts.mkdir(mode=0o700, exist_ok=True)
    try:
        with DockerRuntime({"DOCKER_HOST": endpoint}).client() as client:
            DockerRuntime.recover_receipts(
                client, list(receipts.glob("*.json")), kind="job"
            )
            client.images.resolve(image, expected_id=image)
            if not client.volumes.exists(profile):
                raise RunnerError("native_rollout_binding_invalid")
            listing = _read_job(
                client,
                receipts,
                image,
                profile,
                [
                    "find",
                    str(SESSIONS),
                    "-type",
                    "f",
                    "-links",
                    "1",
                    "-name",
                    f"*{thread_id}*.jsonl",
                ],
                max_bytes=2 * 1024 * 1024,
            )
            try:
                paths = listing.decode("utf-8").splitlines()
            except UnicodeDecodeError:
                raise RunnerError("native_rollout_path_invalid") from None
            if len(paths) != 1:
                raise RunnerError("native_rollout_not_unique")
            path = PurePosixPath(paths[0])
            if not path.is_relative_to(SESSIONS) or ".." in path.parts:
                raise RunnerError("native_rollout_path_invalid")
            size_raw = _read_job(
                client,
                receipts,
                image,
                profile,
                ["stat", "-c", "%s", str(path)],
                max_bytes=4096,
            )
            try:
                size = int(size_raw.strip())
            except ValueError:
                raise RunnerError("native_rollout_size_invalid") from None
            if not 0 < size <= 64 * 1024 * 1024:
                raise RunnerError("native_rollout_size_invalid")
            content = _read_job(
                client, receipts, image, profile, ["cat", str(path)], max_bytes=size
            )
    except CleanupUnconfirmedError:
        raise RunnerError("container_termination_unverified") from None
    except DockerOperationError:
        raise RunnerError("native_rollout_export_failed") from None
    if len(content) != size:
        raise RunnerError("native_rollout_size_invalid")
    try:
        lines = [json.loads(line) for line in content.splitlines()]
    except (ValueError, UnicodeDecodeError):
        raise RunnerError("native_rollout_content_invalid") from None
    first = lines[0] if lines else None
    if (
        not isinstance(first, dict)
        or first.get("type") != "session_meta"
        or not isinstance(first.get("payload"), dict)
        or first["payload"].get("id") != thread_id
    ):
        raise RunnerError("native_rollout_identity_mismatch")
    output = run_dir / "native-rollout.jsonl"
    pending = run_dir / ("native-rollout.pending-" + uuid4().hex)
    pending.write_bytes(content)
    os.replace(pending, output)
    return output


def _read_job(client, receipts, image, profile, command, *, max_bytes):
    """Bound one private read and retain exact cleanup intent on uncertainty."""
    from py_docker.containers.models import ContainerSpec, Mount
    from py_docker.jobs.models import ContainerJob
    from py_docker.streams.models import StreamLimits

    result = DockerRuntime.execute_job(
        client,
        ContainerJob(
            spec=ContainerSpec(
                image=image,
                name="laomedo-rollout-" + uuid4().hex,
                entrypoint=[command[0]],
                command=command[1:],
                user="10001:10001",
                network_mode="none",
                read_only=True,
                cap_drop=["ALL"],
                mounts=[
                    Mount(
                        type="volume",
                        source=profile,
                        target="/home/runner/.codex",
                        read_only=True,
                    )
                ],
            ),
            limits=StreamLimits(seconds=30, max_bytes=max_bytes),
            receipt_path=receipts / (uuid4().hex + ".json"),
            wait_timeout_seconds=5.0,
        ),
    )
    if result.exit_code:
        raise RunnerError("native_rollout_export_failed")
    return result.stdout


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
