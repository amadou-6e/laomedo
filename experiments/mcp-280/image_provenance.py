"""Compare the accepted run's immutable Codex adapter image with owned source."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    args = parser.parse_args()
    root = args.implementation.resolve()
    sys.path.insert(0, str(root / "src"))
    from laomedo.docker import DockerRuntime
    from py_docker.containers.models import ContainerSpec
    from py_docker.jobs.models import ContainerJob
    from py_docker.streams.models import StreamLimits

    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    state = Path(metadata["state"])
    records = []
    for path in (state / "runner/runs").glob("*/record.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("status") == "completed" and record.get("mcp_manifest"):
            records.append((path.stat().st_mtime, record))
    record = max(records, key=lambda item: item[0])[1]
    endpoints = []

    def endpoint_values(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "docker_endpoint" and isinstance(child, str):
                    endpoints.append(child)
                elif isinstance(child, (dict, list)):
                    endpoint_values(child)
        elif isinstance(value, list):
            for child in value:
                endpoint_values(child)

    endpoint_values(record)
    if len(set(endpoints)) != 1:
        raise RuntimeError("recorded_daemon_required")
    runtime = DockerRuntime({"DOCKER_HOST": endpoints[0]})
    result = runtime.run_job(
        ContainerJob(
            spec=ContainerSpec(
                image=record["image_id"],
                name="mcp-280-provenance-" + uuid4().hex[:12],
                command=[
                    "sh",
                    "-c",
                    "cat /opt/acp/adapter-checksums.txt; sha256sum /opt/acp/index.mjs",
                ],
            ),
            limits=StreamLimits(max_bytes=8192, seconds=20),
            receipt_path=state / ("provenance-" + uuid4().hex + ".json"),
            wait_timeout_seconds=20,
        )
    )
    if result.exit_code != 0:
        raise RuntimeError("image_provenance_read_failed")
    checksums = {}
    for line in result.stdout.decode("utf-8").splitlines():
        digest, path = line.split(maxsplit=1)
        checksums[path.strip()] = digest
    sources = {
        "/tmp/native-events.patch": "native-events.patch",
        "src/LaomedoExtension.ts": "LaomedoExtension.ts",
        "src/LaomedoLaunch.ts": "LaomedoLaunch.ts",
    }
    matches = {
        name: checksums[image_path]
        == hashlib.sha256((root / "docker/codex-acp" / name).read_bytes()).hexdigest()
        for image_path, name in sources.items()
    }
    matches["built_adapter"] = (
        checksums["dist/index.js"] == checksums["/opt/acp/index.mjs"]
    )
    print(
        json.dumps(
            {
                "stage": "image_provenance",
                "image_id": record["image_id"],
                "matches": matches,
            }
        ),
        flush=True,
    )
    return 0 if all(matches.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
