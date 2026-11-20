"""Acquire this workstream's image through its actual registered build path."""

from laomedo.docker import DockerRuntime
from laomedo.agents.agents.codex.settings import IMAGE
from laomedo.container_images.errors import ImageBuildError

from docker.errors import ImageNotFound
from laomedo.host.private_state.windows import WindowsDirectorySecurity
from laomedo.host.private_state.utils import _owner_sid
from pathlib import Path

# Owner explicitly authorized repairing this exact directory's owner-only ACL.
security = WindowsDirectorySecurity()
private_builds = Path.home() / ".laomedo-image-builds"
sid = _owner_sid(None)
security.restrict(private_builds, sid)
security.verify(private_builds, sid)
with DockerRuntime(None).client() as client:
    try:
        current = client.sdk.images.get(IMAGE)
    except ImageNotFound:
        current = None
    if current is not None and not (current.labels or {}).get("laomedo.image.recipe"):
        # Preserve the manually built experimental image; remove its tag only.
        current.tag(IMAGE + "-manual-backup")
        client.sdk.images.remove(IMAGE, noprune=True)
    result = DockerRuntime.ensure_image(client, IMAGE)
    image = client.sdk.images.get(result)
    print(
        "registered_image_ready", bool((image.labels or {}).get("laomedo.image.recipe"))
    )
