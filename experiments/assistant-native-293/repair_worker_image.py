"""Owner-authorized stale worker-tag repair, preserving the old image by ID."""

from datetime import datetime, timezone
from pathlib import Path

from laomedo.agents.agents.opencode.settings import WORKER_IMAGE
from laomedo.container_images.registry import ImageRegistry
from laomedo.container_images.settings import ImageBuildSettings
from laomedo.docker import DockerRuntime
from laomedo.host.private_state.windows import WindowsDirectorySecurity


if __name__ == "__main__":
    from docker.errors import ImageNotFound
    import win32api
    import win32security
    import win32con

    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    sid = win32security.ConvertSidToStringSid(win32security.GetTokenInformation(token, win32security.TokenUser)[0])
    private = Path.home() / ".laomedo-image-builds"
    security = WindowsDirectorySecurity()
    security.restrict(private, sid)
    security.verify(private, sid)
    print("owner_only_build_state_verified", flush=True)
    with DockerRuntime(environment=None).connect() as client:
        recipe = ImageRegistry.load().find(WORKER_IMAGE, max_bytes=ImageBuildSettings().context_bytes)
        if recipe is None:
            raise SystemExit("registered_worker_recipe_required")
        try:
            image = client.sdk.images.get(WORKER_IMAGE)
        except ImageNotFound:
            image = None
        if image is not None and (image.labels or {}).get("laomedo.image.recipe") != recipe.fingerprint:
            previous = image.id
            backup = "laomedo-opencode-worker:preserved-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + previous.removeprefix("sha256:")[:12]
            if not image.tag(backup):
                raise SystemExit("backup_tag_failed_original_untouched")
            if client.sdk.images.get(backup).id != previous:
                raise SystemExit("backup_identity_mismatch_original_untouched")
            if client.sdk.images.get(WORKER_IMAGE).id != previous:
                raise SystemExit("worker_tag_changed_original_untouched")
            print("preserved", backup, previous, flush=True)
            client.sdk.images.remove(WORKER_IMAGE, force=False, noprune=True)
            print("removed_stale_tag_only", WORKER_IMAGE, flush=True)
        identity = DockerRuntime.ensure_image(client, WORKER_IMAGE)
        print("verified_current_recipe", identity, flush=True)
