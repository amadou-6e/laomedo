"""Build the registered native-command image without login or model inference."""

from laomedo.agents.agents.codex.settings import IMAGE
from laomedo.docker import DockerRuntime


with DockerRuntime(None).client() as client:
    identity = DockerRuntime.ensure_image(client, IMAGE)
    print({"image": IMAGE, "identity": identity, "model_turns": 0})
