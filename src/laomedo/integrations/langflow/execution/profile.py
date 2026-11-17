"""Supervise network-free native operational APIs separately for each profile."""

import asyncio
import json
import secrets
import threading
from uuid import uuid4

from pydantic import SecretStr

from laomedo.host.leases.client import LeaseClient
from laomedo.host.leases.models import ContainerIdentity
from laomedo.host.leases.settings import LABEL_RUN, LABEL_TOKEN
from laomedo.integrations.langflow.execution.base import BaseDockerRuntime
from laomedo.integrations.langflow.execution.errors import GraphWorkerError
from laomedo.integrations.langflow.execution.models import NativeProfileInstance
from laomedo.integrations.langflow.execution.settings import (
    NATIVE_PROFILE_DEPLOYMENT_LABEL,
    NATIVE_PROFILE_OWNER_LABEL,
    NATIVE_PROFILE_STATE_PATH,
    NATIVE_PROFILE_PORT,
)


class DockerProfileRuntime(BaseDockerRuntime):
    """Keep operational volumes disjoint from broker authentication and custody."""

    def __init__(self, settings):
        """Use one explicit deployment namespace and an independent lease service."""
        super().__init__(settings)
        self.instances = {}
        self._locks = {}

    def _volume_name(self, owner_id):
        """Derive only a host-selected deployment/owner namespace, never a posted path."""
        return "laomedo-graphs-" + self.settings.deployment_id.hex + "-" + owner_id.hex

    async def _volume(self, owner_id, environment):
        """Create or verify an ordinary local volume; never adopt host-backed storage."""
        name = self._volume_name(owner_id)
        result = await self._control(
            [
                "volume",
                "create",
                "--driver",
                "local",
                "--label",
                NATIVE_PROFILE_DEPLOYMENT_LABEL
                + "="
                + str(self.settings.deployment_id),
                "--label",
                NATIVE_PROFILE_OWNER_LABEL + "=" + str(owner_id),
                name,
            ],
            environment,
        )
        if result.returncode:
            raise GraphWorkerError()
        inspected = await self._control(["volume", "inspect", name], environment)
        if inspected.returncode:
            raise GraphWorkerError()
        volume = json.loads(inspected.stdout)[0]
        labels = volume.get("Labels") or {}
        if (
            volume.get("Name") != name
            or volume.get("Driver") != "local"
            or volume.get("Scope") != "local"
            or volume.get("Options")
            or labels.get(NATIVE_PROFILE_DEPLOYMENT_LABEL)
            != str(self.settings.deployment_id)
            or labels.get(NATIVE_PROFILE_OWNER_LABEL) != str(owner_id)
        ):
            raise GraphWorkerError()
        return name

    def _verify_profile(self, entry, volume):
        """Admit exactly one verified operational volume and no host mounts."""
        self._verify_limits(entry)
        mounts = entry.get("Mounts") or []
        if (
            entry["Config"].get("Volumes")
            or entry["HostConfig"].get("Binds")
            or len(mounts) != 1
        ):
            raise GraphWorkerError()
        mount = mounts[0]
        if (
            mount.get("Type") != "volume"
            or mount.get("Name") != volume
            or mount.get("Driver") != "local"
            or mount.get("RW") is not True
            or mount.get("Destination") != NATIVE_PROFILE_STATE_PATH
        ):
            raise GraphWorkerError()

    async def _ready(self, instance, environment):
        """Check container-loopback readiness without cookies, JWTs or host ports."""
        deadline = (
            asyncio.get_running_loop().time() + self.settings.startup_timeout_seconds
        )
        program = (
            "from urllib.request import urlopen; "
            "print(urlopen('http://127.0.0.1:"
            + str(NATIVE_PROFILE_PORT)
            + "/api/v1/users/whoami', timeout=2).read().decode())"
        )
        while asyncio.get_running_loop().time() < deadline:
            if instance.cancelled.is_set():
                raise GraphWorkerError()
            remaining = deadline - asyncio.get_running_loop().time()
            try:
                result = await asyncio.wait_for(
                    self._control(
                        ["exec", instance.container_id, "python", "-I", "-c", program],
                        environment,
                    ),
                    timeout=remaining,
                )
            except asyncio.TimeoutError:
                raise GraphWorkerError() from None
            if result.returncode == 0:
                data = json.loads(result.stdout)
                if data.get("id") != str(instance.owner_id):
                    raise GraphWorkerError()
                return
            await asyncio.sleep(0.2)
        raise GraphWorkerError()

    async def acquire(self, scope):
        """Admit a live owner before creating or reusing only their native runtime."""
        await scope.revalidate()
        lock = self._locks.setdefault(scope.owner_id, asyncio.Lock())
        async with lock:
            instance = self.instances.get(scope.owner_id)
            if instance is None:
                instance = await self._start(scope.owner_id)
                self.instances[scope.owner_id] = instance
            if instance.cancelled.is_set():
                raise GraphWorkerError()
            await scope.revalidate()
            return instance

    async def _start(self, owner_id):
        """Verify isolation before starting a fresh native server with no broker state."""
        environment = self._environment()
        await self._local_context(environment)
        volume = await self._volume(owner_id, environment)
        identity = ContainerIdentity(
            name="laomedo-profile-" + uuid4().hex,
            run_id=str(uuid4()),
            token=SecretStr(secrets.token_hex(16)),
        )
        cancelled = threading.Event()
        lease = None
        try:
            registration = asyncio.create_task(
                asyncio.to_thread(
                    LeaseClient,
                    self.settings.lease_state,
                    run_id=identity.run_id,
                    name=identity.name,
                    token=identity.token.get_secret_value(),
                    cancelled=cancelled,
                )
            )
            try:
                lease = await asyncio.shield(registration)
            except asyncio.CancelledError:
                lease = await asyncio.shield(registration)
                raise
            created = await self._control(
                [
                    "create",
                    "--pull=never",
                    "--init",
                    "--name",
                    identity.name,
                    "--label",
                    LABEL_RUN + "=" + identity.run_id,
                    "--label",
                    LABEL_TOKEN + "=" + identity.token.get_secret_value(),
                    "--network=none",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "--read-only",
                    "--user",
                    "65532:65532",
                    "--pids-limit",
                    str(self.settings.pids),
                    "--memory",
                    str(self.settings.memory_mib) + "m",
                    "--cpus",
                    str(self.settings.cpus),
                    "--tmpfs",
                    "/tmp:rw,nosuid,nodev,size="
                    + str(self.settings.temporary_mib)
                    + "m",
                    "--mount",
                    "type=volume,source="
                    + volume
                    + ",target="
                    + NATIVE_PROFILE_STATE_PATH,
                    self.settings.image_id,
                    "--owner-id",
                    str(owner_id),
                    "--state-root",
                    NATIVE_PROFILE_STATE_PATH,
                ],
                environment,
            )
            if created.returncode:
                raise GraphWorkerError()
            entry = await self._inspect(identity, environment)
            self._verify_profile(entry, volume)
            started = await self._control(["start", entry["Id"]], environment)
            if started.returncode:
                raise GraphWorkerError()
            instance = NativeProfileInstance(
                owner_id=owner_id,
                container_id=entry["Id"],
                identity=identity,
                volume=volume,
                lease=lease,
                cancelled=cancelled,
            )
            await self._ready(instance, environment)
            return instance
        except BaseException:
            try:
                await self._remove(identity, environment)
            finally:
                if lease is not None:
                    await asyncio.to_thread(lease.finish)
            raise

    async def stop(self, owner_id):
        """End only this owner's exact container; preserve its operational volume."""
        lock = self._locks.setdefault(owner_id, asyncio.Lock())
        async with lock:
            instance = self.instances.pop(owner_id, None)
            if instance is None:
                return
            instance.cancelled.set()
            try:
                await self._remove(instance.identity, self._environment())
            finally:
                await asyncio.to_thread(instance.lease.finish)

    async def close(self):
        """Clean up all containers registered by this broker, retaining history."""
        results = await asyncio.gather(
            *(self.stop(owner_id) for owner_id in tuple(self.instances)),
            return_exceptions=True,
        )
        if any(isinstance(result, BaseException) for result in results):
            raise GraphWorkerError()
