"""Real isolated native operational APIs, without broker profiles or GitHub."""

import os
import subprocess
import unittest


@unittest.skipUnless(
    os.environ.get("LAOMEDO_TEST_NATIVE_RUNTIME_IMAGE"),
    "An explicitly built native runtime image is required",
)
class NativeProfileContainerTests(unittest.TestCase):
    """Container startup/CRUD is integration evidence, not GitHub acceptance."""

    def test_native_store_uses_only_its_operational_owner_and_has_no_private_routes(
        self,
    ):
        image = os.environ["LAOMEDO_TEST_NATIVE_RUNTIME_IMAGE"]
        self.assertRegex(image, r"^sha256:[0-9a-f]{64}$")
        program = r"""
import asyncio
from pathlib import Path
from uuid import uuid4
from httpx import ASGITransport, AsyncClient
from laomedo.integrations.langflow.execution.native import NativeProfileRuntime
from laomedo.integrations.langflow.execution.settings import NativeProfileSettings

async def verify():
    owner, unrelated = uuid4(), uuid4()
    runtime = NativeProfileRuntime(NativeProfileSettings(
        owner_id=owner, state_root=Path("/tmp/operational-store")))
    app = runtime.create_app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://native") as client:
            user = await client.get("/api/v1/users/whoami")
            assert user.status_code == 200, "operational_identity_failed"
            assert user.json()["id"] == str(owner)
            assert "password" not in user.json()
            created = await client.post("/api/v1/flows/", json={
                "name": "Isolated workspace", "user_id": str(unrelated),
                "data": {"nodes": [], "edges": []}})
            assert created.status_code == 201, "operational_create_failed"
            flow = created.json()
            assert flow["user_id"] == str(owner)
            fetched = await client.get("/api/v1/flows/" + flow["id"])
            assert fetched.status_code == 200
            assert fetched.json()["user_id"] == str(owner)
            for path in ("/api/v1/laomedo/github-connections", "/api/v1/laomedo/private-session"):
                response = await client.get(path)
                assert response.status_code == 404, "broker_route_present_in_graph_runtime"
    print("NATIVE_PROFILE_CHECK_OK")

asyncio.run(verify())
"""
        result = subprocess.run(
            [
                "docker",
                "--context",
                "desktop-linux",
                "run",
                "--rm",
                "--interactive",
                "--network=none",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--read-only",
                "--user",
                "65532:65532",
                "--pids-limit",
                "256",
                "--memory",
                "2g",
                "--cpus",
                "2",
                "--tmpfs",
                "/tmp:rw,nosuid,nodev,size=256m",
                "--entrypoint",
                "python",
                image,
                "-",
            ],
            input=program,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        # Native diagnostics stay local; never echo them into public CI output.
        self.assertEqual(result.returncode, 0, "Isolated native startup/CRUD failed")
        self.assertIn("NATIVE_PROFILE_CHECK_OK", result.stdout)
