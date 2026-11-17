"""Local Docker control shared by isolated native runtime owners."""

import asyncio
import json
import os
import re
import subprocess

from laomedo.host.leases.settings import LABEL_RUN, LABEL_TOKEN
from laomedo.integrations.langflow.execution.errors import GraphWorkerError
from laomedo.integrations.langflow.execution.settings import (
    DOCKER_CONTROL_OUTPUT_BYTES,
    DOCKER_CONTROL_CHUNK_BYTES,
)


class BaseDockerRuntime:
    """Control only a configured local daemon and exact labelled containers."""

    def __init__(self, settings):
        """Retain explicit admitted host deployment settings only."""
        self.settings = settings

    def _environment(self):
        """Pass only Docker-client/OS configuration; never account or model tokens."""
        allowed = {
            "PATH",
            "SYSTEMROOT",
            "WINDIR",
            "HOME",
            "USERPROFILE",
            "APPDATA",
            "LOCALAPPDATA",
            "TEMP",
            "TMP",
            "DOCKER_CONFIG",
            "DOCKER_CERT_PATH",
        }
        environment = {
            key: value for key, value in os.environ.items() if key.upper() in allowed
        }
        environment["DOCKER_CONTEXT"] = self.settings.docker_context
        return environment

    async def _control(self, arguments, environment):
        """Run bounded Docker control I/O without returning private diagnostics."""
        process = await asyncio.create_subprocess_exec(
            "docker",
            *arguments,
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        readers = [
            asyncio.create_task(self._control_output(stream))
            for stream in (process.stdout, process.stderr)
        ]
        try:
            stdout, stderr = await asyncio.wait_for(
                asyncio.gather(*readers), timeout=self.settings.control_timeout_seconds
            )
            await asyncio.wait_for(
                process.wait(), timeout=self.settings.control_timeout_seconds
            )
        except BaseException:
            if process.returncode is None:
                process.kill()
            for reader in readers:
                reader.cancel()
            await asyncio.gather(*readers, return_exceptions=True)
            # After killing the local Docker client, drain its bounded pipe
            # buffers so wait cannot hang on a paused StreamReader transport.
            await asyncio.wait_for(
                process.communicate(), timeout=self.settings.control_timeout_seconds
            )
            raise
        return subprocess.CompletedProcess(
            arguments, process.returncode, stdout, stderr
        )

    async def _control_output(self, stream):
        """Bound even container-influenced readiness output before retaining bytes."""
        output = bytearray()
        while True:
            chunk = await stream.read(DOCKER_CONTROL_CHUNK_BYTES)
            if not chunk:
                return bytes(output)
            if len(output) + len(chunk) > DOCKER_CONTROL_OUTPUT_BYTES:
                raise GraphWorkerError()
            output.extend(chunk)

    async def _local_context(self, environment):
        """Refuse remote Docker daemons before private job data can leave the host."""
        result = await self._control(
            [
                "context",
                "inspect",
                self.settings.docker_context,
                "--format",
                "{{json .Endpoints.docker.Host}}",
            ],
            environment,
        )
        if result.returncode or json.loads(result.stdout) not in {
            "npipe:////./pipe/docker_engine",
            "npipe:////./pipe/dockerDesktopLinuxEngine",
            "unix:///var/run/docker.sock",
        }:
            raise GraphWorkerError()

    async def _inspect(self, identity, environment):
        """Return only an exact labelled reservation; unknown errors are not absence."""
        result = await self._control(["inspect", identity.name], environment)
        if result.returncode:
            if (
                b"no such object:" in result.stderr.lower()
                or b"no such container:" in result.stderr.lower()
            ):
                return None
            raise GraphWorkerError()
        entry = json.loads(result.stdout)[0]
        labels = entry["Config"].get("Labels") or {}
        if (
            entry["Name"].lstrip("/") != identity.name
            or labels.get(LABEL_RUN) != identity.run_id
            or labels.get(LABEL_TOKEN) != identity.token.get_secret_value()
            or not re.fullmatch(r"[0-9a-f]{64}", entry.get("Id", ""))
        ):
            raise GraphWorkerError()
        return entry

    async def _remove(self, identity, environment):
        """Delete only this verified container ID, then prove its reservation absent."""
        entry = await self._inspect(identity, environment)
        if entry is None:
            return
        await self._control(["rm", "--force", entry["Id"]], environment)
        if await self._inspect(identity, environment) is not None:
            raise GraphWorkerError()

    def _verify_limits(self, entry):
        """Verify actual daemon configuration before injecting any job capability."""
        if not isinstance(entry, dict):
            raise GraphWorkerError()
        config, host = entry["Config"], entry["HostConfig"]
        if (
            config["Image"] != self.settings.image_id
            or config.get("User") != "65532:65532"
            or host.get("Privileged")
            or host.get("CapAdd")
            or host.get("VolumesFrom")
            or host.get("DeviceRequests")
            or host.get("NetworkMode") != "none"
            or not host.get("ReadonlyRootfs")
            or "ALL" not in (host.get("CapDrop") or [])
            or not {"no-new-privileges", "no-new-privileges=true"}.intersection(
                host.get("SecurityOpt") or []
            )
            or host.get("PidMode", "") not in {"", "private"}
            or host.get("IpcMode", "") not in {"", "private"}
            or host.get("Devices")
            or host.get("Memory") != self.settings.memory_mib * 1024 * 1024
            or host.get("PidsLimit") != self.settings.pids
            or host.get("NanoCpus") != int(self.settings.cpus * 1_000_000_000)
            or host.get("PortBindings")
            or host.get("Tmpfs")
            != {
                "/tmp": "rw,nosuid,nodev,size=" + str(self.settings.temporary_mib) + "m"
            }
        ):
            raise GraphWorkerError()
