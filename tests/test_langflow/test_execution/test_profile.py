"""Real persistent operational runtime isolation; no broker profiles or GitHub."""

import asyncio
import json
import os
import subprocess
import unittest
from uuid import uuid4

from support.leases import LeaseServiceProcess

from laomedo.github.connections.models import GitHubConnectionScope
from laomedo.integrations.langflow.execution.profile import DockerProfileRuntime
from laomedo.integrations.langflow.execution.settings import (
    NativeProfileDeploymentSettings,
    NATIVE_PROFILE_DEPLOYMENT_LABEL,
    NATIVE_PROFILE_OWNER_LABEL,
)


@unittest.skipUnless(
    os.environ.get("LAOMEDO_TEST_NATIVE_RUNTIME_IMAGE"),
    "An explicitly built native runtime image is required",
)
class DockerProfileRuntimeTests(unittest.IsolatedAsyncioTestCase):
    """Verify live supervision, distinct owner volumes and retained flow definitions."""

    async def revalidate(self):
        """Synthetic host admission only; real browser admission is tested elsewhere."""

    def scope(self, owner):
        """Provide no browser token, PIN, GitHub credential or reusable authority."""
        return GitHubConnectionScope(
            owner_id=owner, lease_binding="synthetic-lease", check=self.revalidate
        )

    async def call(self, instance, method, path, body=None):
        """Call only container loopback through a private exec stdin, without host ports."""
        program = (
            "import gzip,json,sys;from urllib.request import Request,urlopen;"
            "value=json.load(sys.stdin);"
            "body=json.dumps(value['body']).encode() if value['body'] is not None else None;"
            "request=Request('http://127.0.0.1:7860'+value['path'],data=body,method=value['method'],"
            "headers={'Content-Type':'application/json'});"
            "response=urlopen(request,timeout=10);data=response.read();"
            "data=gzip.decompress(data) if response.headers.get('Content-Encoding')=='gzip' else data;"
            "print(data.decode())"
        )
        result = await asyncio.to_thread(
            subprocess.run,
            [
                "docker",
                "--context",
                "desktop-linux",
                "exec",
                "--interactive",
                instance.container_id,
                "python",
                "-I",
                "-c",
                program,
            ],
            input=json.dumps({"method": method, "path": path, "body": body}),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, "Native operational API request failed")
        return json.loads(result.stdout)

    async def test_owner_volumes_preserve_flow_definitions_across_runtime_restart(self):
        first, second, deployment = uuid4(), uuid4(), uuid4()
        with LeaseServiceProcess() as service:
            runtime = DockerProfileRuntime(
                NativeProfileDeploymentSettings(
                    image_id=os.environ["LAOMEDO_TEST_NATIVE_RUNTIME_IMAGE"],
                    lease_state=service.state,
                    deployment_id=deployment,
                )
            )
            try:
                primary = await runtime.acquire(self.scope(first))
                created = await self.call(
                    primary,
                    "POST",
                    "/api/v1/flows/",
                    {
                        "name": "Retained synthetic flow",
                        "data": {"nodes": [], "edges": []},
                    },
                )
                self.assertEqual(created["user_id"], str(first))
                await runtime.stop(first)
                other = await runtime.acquire(self.scope(second))
                self.assertNotEqual(primary.volume, other.volume)
                listing = await self.call(other, "GET", "/api/v1/flows/")
                self.assertNotIn("Retained synthetic flow", json.dumps(listing))
                await runtime.stop(second)
                resumed = await runtime.acquire(self.scope(first))
                self.assertNotEqual(primary.container_id, resumed.container_id)
                self.assertEqual(primary.volume, resumed.volume)
                fetched = await self.call(
                    resumed, "GET", "/api/v1/flows/" + created["id"]
                )
                self.assertEqual(fetched["name"], "Retained synthetic flow")
                self.assertEqual(fetched["user_id"], str(first))
            finally:
                await runtime.close()
                # Only this test's fresh namespace can be removed. Production
                # container shutdown deliberately preserves its owner's volume.
                for owner in (first, second):
                    name = runtime._volume_name(owner)
                    inspected = await asyncio.to_thread(
                        subprocess.run,
                        [
                            "docker",
                            "--context",
                            "desktop-linux",
                            "volume",
                            "inspect",
                            name,
                        ],
                        capture_output=True,
                        timeout=15,
                    )
                    if inspected.returncode:
                        self.assertIn(b"no such volume", inspected.stderr.lower())
                        continue
                    labels = json.loads(inspected.stdout)[0].get("Labels") or {}
                    self.assertEqual(
                        labels.get(NATIVE_PROFILE_DEPLOYMENT_LABEL), str(deployment)
                    )
                    self.assertEqual(labels.get(NATIVE_PROFILE_OWNER_LABEL), str(owner))
                    removed = await asyncio.to_thread(
                        subprocess.run,
                        [
                            "docker",
                            "--context",
                            "desktop-linux",
                            "volume",
                            "rm",
                            name,
                        ],
                        capture_output=True,
                        timeout=15,
                    )
                    self.assertEqual(
                        removed.returncode,
                        0,
                        "Test-owned operational volume cleanup failed",
                    )
