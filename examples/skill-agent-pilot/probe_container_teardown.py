"""Real no-model check that owned SDK session close removes its exact ID."""
from pathlib import Path
import tempfile
from uuid import uuid4
from py_docker import Client
from py_docker.containers.models import ContainerSpec
from py_docker.sessions.models import ContainerSession
from py_docker.streams.models import StreamLimits
from laomedo.agents.providers.codex.settings import IMAGE


def main():
    """Launch an inert process and confirm exact cleanup without credentials."""
    with tempfile.TemporaryDirectory(prefix="laomedo-teardown-") as directory, Client() as client:
        spec=ContainerSpec(image=client.images.resolve(IMAGE),name="laomedo-teardown-"+uuid4().hex,
                           stdin_open=True,command=["sh","-c","sleep 60"])
        with client.sessions.open(ContainerSession(spec=spec,limits=StreamLimits(seconds=20,max_bytes=1024),
                receipt_path=Path(directory).joinpath("receipt.json"))) as session:
            if not session.state().running:
                raise RuntimeError("owned_container_never_started")
        if not session.state().removed:
            raise RuntimeError("owned_container_survived_close")
        print("owned_container_removed; model_turns_submitted=0")


if __name__ == "__main__":
    main()
