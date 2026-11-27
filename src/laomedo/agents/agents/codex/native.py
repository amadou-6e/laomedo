"""Owned native Codex credential profiles and cross-process writer custody."""

import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

from laomedo.agents.agents.codex.models import CodexNativeProfile
from laomedo.agents.connections.errors import ProviderConnectionError
from laomedo.docker import DockerRuntime
from laomedo.host.credentials.siwc.utils import _atomic_private


class CodexNativeCredentials:
    """Own a revision's volume without inspecting or exporting native tokens.

    A lease is held until the caller has confirmed native cleanup. Every creator
    registers its exact receipt before launch. The next writer first reconciles
    those receipts, including after process loss; a Python lock alone is not proof
    that an earlier container stopped.
    """

    def __init__(self, root: Path):
        """Bind an already protected host revision directory; perform no Docker I/O."""
        self.root = Path(root)
        self._owner = None

    def descriptor(self) -> CodexNativeProfile:
        """Read nonsecret ownership metadata, never the native credential file."""
        try:
            return CodexNativeProfile.model_validate_json(
                (self.root / "codex-custody.json").read_bytes()
            )
        except (OSError, ValueError):
            raise ProviderConnectionError("provider_connection_unavailable") from None

    def create(self, docker, connection_id: UUID, credential_id: UUID, image_id: str):
        """Record exact ownership before possibly ambiguous daemon creation."""
        from py_docker.settings import OWNERSHIP_LABEL

        if (self.root / "codex-custody.json").exists():
            raise ProviderConnectionError("provider_request_refused")
        descriptor = CodexNativeProfile(
            name="laomedo-codex-connection-" + credential_id.hex,
            labels={
                "laomedo.provider": "codex",
                "laomedo.connection": str(connection_id),
                OWNERSHIP_LABEL: uuid4().hex,
            },
            docker_endpoint=docker.connection.endpoint,
            image_id=image_id,
        )
        _atomic_private(self.root / "codex-custody.json", descriptor.model_dump())
        docker.sdk.volumes.create(name=descriptor.name, labels=descriptor.labels)
        if docker.volumes.inspect(self._identity(descriptor)) is None:
            raise ProviderConnectionError("provider_cleanup_unconfirmed")
        return descriptor

    def profile(self) -> CodexNativeProfile:
        """Require the admitted owned volume; never create a missing replacement."""
        descriptor = self.descriptor()
        with self._client(descriptor) as docker:
            if docker.volumes.inspect(self._identity(descriptor)) is None:
                raise ProviderConnectionError("provider_connection_unavailable")
        return descriptor

    @contextmanager
    def lease(self, *, require_volume=True):
        """Refuse another writer and recover crash-left exact receipts before use."""
        fd = os.open(self.root / "native-writer.lock", os.O_CREAT | os.O_RDWR, 0o600)
        locked = False
        try:
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"0")
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise ProviderConnectionError("provider_connection_busy") from None
            locked = True
            self._owner = threading.get_ident()
            descriptor = self.descriptor()
            with self._client(descriptor) as docker:
                self._recover(docker)
                if (
                    require_volume
                    and docker.volumes.inspect(self._identity(descriptor)) is None
                ):
                    raise ProviderConnectionError("provider_connection_unavailable")
            yield descriptor
        finally:
            if locked:
                self._owner = None
                os.lseek(fd, 0, os.SEEK_SET)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def register(self, receipt: Path, *, kind: str = "session") -> None:
        """Persist a creator's exact receipt before launch, only under writer custody."""
        if self._owner != threading.get_ident() or kind not in {"session", "job"}:
            raise ProviderConnectionError("provider_request_refused")
        receipt = Path(receipt).resolve()
        entries = self._receipts()
        entry = {"path": str(receipt), "kind": kind}
        if entry not in entries:
            entries.append(entry)
            _atomic_private(self.root / "native-receipts.json", {"receipts": entries})

    def erase(self) -> None:
        """Recover registered clients and remove only the exact labelled revision."""
        with self.lease(require_volume=False) as descriptor:
            with self._client(descriptor) as docker:
                identity = self._identity(descriptor)
                volume = docker.volumes.inspect(identity)
                if volume is not None:
                    volume.remove(force=False)
                if docker.volumes.inspect(identity) is not None:
                    raise ProviderConnectionError("provider_cleanup_unconfirmed")
            (self.root / "codex-custody.json").unlink()

    def _receipts(self):
        """Load host-owned cleanup references; malformed custody never means empty."""
        path = self.root / "native-receipts.json"
        if not path.exists():
            return []
        try:
            value = json.loads(path.read_bytes())
            entries = value["receipts"]
            if not isinstance(entries, list) or any(
                not isinstance(item, dict)
                or set(item) != {"path", "kind"}
                or item["kind"] not in {"session", "job"}
                or not isinstance(item["path"], str)
                or not Path(item["path"]).is_absolute()
                for item in entries
            ):
                raise ValueError()
            return entries
        except (OSError, ValueError, TypeError, KeyError):
            raise ProviderConnectionError("provider_cleanup_unconfirmed") from None

    def _recover(self, docker):
        """Recover only registered creator receipts before granting a new writer."""
        for entry in self._receipts():
            path = Path(entry["path"])
            if path.exists():
                DockerRuntime.recover_receipts(docker, [path], kind=entry["kind"])
        _atomic_private(self.root / "native-receipts.json", {"receipts": []})

    @staticmethod
    def _client(descriptor):
        """Connect only to the original daemon recorded before credential creation."""
        return DockerRuntime(
            environment={"DOCKER_HOST": descriptor.docker_endpoint}
        ).connect()

    @staticmethod
    def _identity(descriptor):
        """Reconstruct the SDK's ownership-checked volume identity."""
        from py_docker.volumes.models import VolumeIdentity

        return VolumeIdentity(name=descriptor.name, labels=descriptor.labels)
