"""Exercise real native broker identity services in a disposable child runtime."""

import asyncio
from pathlib import Path
import os

from httpx import ASGITransport, AsyncClient

from laomedo.integrations.langflow.authentication.broker import PrivateBrokerRuntime
from laomedo.integrations.langflow.authentication.settings import PrivateBrowserSettings
from laomedo.integrations.langflow.local_profiles.runtime import LocalProfileRuntime


class BrokerStartupCheck:
    """Check native auth/lease composition without a listener or provider calls."""

    async def run(self):
        """Create one synthetic profile, sign in, read custody status and sign out."""
        root = Path(os.environ["LAOMEDO_LOCAL_PROFILE_RUNTIME"])
        origin = "http://127.0.0.1:27889"
        app = PrivateBrokerRuntime(
            LocalProfileRuntime(root),
            PrivateBrowserSettings(
                origin=origin,
                runtime_root=root / "private-github",
                public_roots=(root / "registry",),
            ),
        ).create_app()
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url=origin,
                headers={"origin": origin, "sec-fetch-site": "same-origin"},
            ) as client:
                response = await client.post(
                    "/api/v1/laomedo/profiles",
                    json={
                        "name": "Broker fixture",
                        "pin": "123456",
                        "confirmation": "123456",
                    },
                )
                assert response.status_code == 201, "profile creation failed"
                response = await client.post(
                    "/api/v1/login",
                    data={"username": "Broker fixture", "password": "123456"},
                )
                assert response.status_code == 200, "native login failed"
                response = await client.get("/api/v1/laomedo/private-session")
                assert response.status_code == 200, "private lease unavailable"
                assert response.json().get("ready") is True, "private lease not ready"
                response = await client.get("/api/v1/laomedo/github-connections")
                assert response.status_code == 200, "empty connection inventory failed"
                for path in ("/api/v2/workflows", "/api/v1/custom_component/update"):
                    response = await client.post(path, json={})
                    assert response.status_code == 404, "graph endpoint entered broker"
                response = await client.post("/api/v1/logout")
                assert response.status_code == 200, "native logout failed"
                response = await client.get("/api/v1/laomedo/private-session")
                assert response.status_code != 200, "logout retained private admission"


if __name__ == "__main__":
    asyncio.run(BrokerStartupCheck().run())
