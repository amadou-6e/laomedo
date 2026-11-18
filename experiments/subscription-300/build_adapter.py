"""Explicit operator build from immutable registered inputs; no credential or model use."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path("C:/CodeWorkspace/laomedo")
APP = ROOT / ".tools/worktrees/subscription-300"
sys.path.insert(0, str(APP / "src"))
from laomedo.container_images.registry import ImageRegistry
from laomedo.container_images.settings import ImageBuildSettings
from laomedo.docker import DockerRuntime
from laomedo.agents.agents.codex.settings import IMAGE

settings = ImageBuildSettings()
recipe = ImageRegistry.load().find(IMAGE, max_bytes=settings.context_bytes)
with tempfile.TemporaryDirectory(prefix="laomedo-quota-adapter-") as folder:
    recipe.write_context(Path(folder))
    subprocess.run(
        [
            "docker",
            "build",
            "--label",
            "laomedo.image.recipe=" + recipe.fingerprint,
            "--tag",
            IMAGE,
            "--file",
            str(Path(folder) / recipe.registration.dockerfile),
            folder,
        ],
        check=True,
        timeout=settings.build_seconds,
    )
with DockerRuntime(environment=None).connect() as client:
    image_id = DockerRuntime.ensure_image(client, IMAGE)
    print(
        json.dumps(
            {"stage": "registered_image_admitted", "image": IMAGE, "image_id": image_id}
        ),
        flush=True,
    )
subprocess.run(
    [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        IMAGE,
        "codex",
        "--version",
    ],
    check=True,
    timeout=60,
)
