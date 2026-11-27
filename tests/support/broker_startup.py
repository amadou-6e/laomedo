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

    @staticmethod
    def route_paths(app):
        """Inspect the full real runtime inventory, including native lazy routers."""
        paths = set()
        pending = list(app.routes)
        while pending:
            route = pending.pop()
            candidates = getattr(route, "effective_candidates", None)
            if candidates is not None:
                pending.extend(candidates())
            else:
                paths.add(route.path)
        return paths

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
        assert self.route_paths(app) == {
            "/api/v1/login",
            "/api/v1/refresh",
            "/api/v1/logout",
            "/api/v1/session",
            "/api/v1/users/whoami",
            "/api/v1/laomedo/profile-mode",
            "/api/v1/laomedo/profiles",
            "/api/v1/laomedo/provider-connections",
            "/api/v1/laomedo/provider-connections/graphs/{flow_id}",
            "/api/v1/laomedo/provider-connections/attempts",
            "/api/v1/laomedo/provider-connections/opencode-go",
            "/api/v1/laomedo/provider-connections/claude/attempts/{attempt_id}",
            "/api/v1/laomedo/provider-connections/claude/attempts/{attempt_id}/code",
            "/api/v1/laomedo/provider-connections/{connection_id}/disconnect",
            "/api/v1/laomedo/provider-connections/{connection_id}/cleanup",
            "/api/v1/laomedo/provider-connections/attempts/{attempt_id}",
            "/api/v1/laomedo/provider-connections/attempts/{attempt_id}/cancel",
            "/auth/callback",
            "/api/v1/laomedo/private-session",
            "/api/v1/laomedo/github-connections-capability",
            "/api/v1/laomedo/github-connections",
            "/api/v1/laomedo/github-connections/{action}",
            "/api/v1/laomedo/github-connections/callback",
            "/api/v1/laomedo/github-connections/app-registration/callback",
            "/api/v1/laomedo/private-skills/{action}",
            "/api/v1/laomedo/private-github-nodes/{action}",
        }, "broker runtime installed an unexpected endpoint"
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
                response = await client.get("/api/v1/auto_login")
                assert response.status_code == 404, "native auto-login entered broker"
                for path in ("/api/v2/workflows", "/api/v1/custom_component/update"):
                    response = await client.post(path, json={})
                    assert response.status_code == 404, "graph endpoint entered broker"
                response = await client.post("/api/v1/logout")
                assert response.status_code == 200, "native logout failed"
                response = await client.get("/api/v1/laomedo/private-session")
                assert response.status_code != 200, "logout retained private admission"


class ProviderBrokerStartupCheck(BrokerStartupCheck):
    """Real profile and data-only Flow HTTP path, without providers or inference."""

    async def run(self):
        from laomedo.integrations.langflow.authentication.provider import (
            ProviderBrokerRuntime,
        )
        from laomedo.integrations.langflow.execution.providers.settings import (
            ProviderAppSettings,
        )
        from laomedo.integrations.langflow.execution.worker.settings import (
            GraphWorkerSettings,
        )

        root = Path(os.environ["LAOMEDO_LOCAL_PROFILE_RUNTIME"])
        source, frontend = root.parent / "source", root.parent / "frontend"
        source.mkdir()
        (frontend / "assets").mkdir(parents=True)
        (frontend / "index.html").write_text("Provider broker startup fixture")
        origin = "http://127.0.0.1:27889"
        app = ProviderBrokerRuntime(
            LocalProfileRuntime(root, provider_source=source),
            PrivateBrowserSettings(
                origin=origin,
                runtime_root=root / "private-github",
                public_roots=(frontend, root / "registry"),
            ),
            ProviderAppSettings(
                components=Path(__file__).resolve().parents[2] / "components",
                frontend=frontend,
                worker=GraphWorkerSettings(
                    image_id="sha256:" + "a" * 64, lease_state=root / "leases"
                ),
            ),
        ).create_app()
        from laomedo.integrations.langflow.local_profiles.cookies import (
            ProfileCookieBoundary,
        )

        assert app.user_middleware[0].cls is ProfileCookieBoundary
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url=origin,
                headers={"origin": origin, "sec-fetch-site": "same-origin"},
            ) as client:
                response = await client.post(
                    "/api/v1/laomedo/profiles",
                    json={
                        "name": "Provider fixture",
                        "pin": "123456",
                        "confirmation": "123456",
                    },
                )
                assert (
                    response.status_code == 201
                ), "provider fixture profile creation failed"
                response = await client.post(
                    "/api/v1/login",
                    data={"username": "Provider fixture", "password": "123456"},
                )
                assert response.status_code == 200, "provider fixture login failed"
                response = await client.get("/api/v1/laomedo/private-session")
                assert (
                    response.status_code == 200 and response.json().get("ready") is True
                ), "provider fixture private lease unavailable"
                response = await client.get("/api/v1/all")
                assert response.status_code == 200, "curated metadata unavailable"
                registry = response.json()
                assert (
                    "LaomedoCodexAgent" in registry["laomedo"]
                ), "curated Agent absent"
                template = registry["input_output"]["TextInput"]
                graph = {
                    "nodes": [
                        {
                            "id": "text-fixture",
                            "type": "genericNode",
                            "data": {
                                "id": "text-fixture",
                                "type": "TextInput",
                                "node": template,
                            },
                        }
                    ],
                    "edges": [],
                }
                response = await client.post(
                    "/api/v1/flows/",
                    json={"name": "Provider fixture flow", "data": graph},
                )
                assert response.status_code == 200, "data-only flow creation failed"
                identifier = response.json()["id"]
                graph["nodes"][0]["data"]["node"]["template"]["input_value"][
                    "value"
                ] = "Edited fixture"
                response = await client.patch(
                    "/api/v1/flows/" + identifier, json={"data": graph}
                )
                assert response.status_code == 200, "data-only flow edit failed"
                response = await client.get("/api/v1/flows/" + identifier)
                assert (
                    response.status_code == 200 and response.json()["data"] == graph
                ), "saved graph differs"
                for path in (
                    "/api/v1/custom_component/update",
                    "/api/v1/validate/code",
                    "/api/v2/workflows",
                ):
                    response = await client.post(path, json={"code": "not executed"})
                    assert response.status_code in (
                        404,
                        405,
                    ), "untrusted native API entered broker"
                response = await client.post("/api/v1/logout")
                assert response.status_code == 200, "provider fixture logout failed"


if __name__ == "__main__":
    import sys

    scenario = (
        ProviderBrokerStartupCheck()
        if sys.argv[1:] == ["providers"]
        else BrokerStartupCheck()
    )
    try:
        asyncio.run(scenario.run())
    except Exception as error:
        # Keep native login diagnostics private. Emit only exception type and
        # stack locations, without messages, values or local variables.
        import json
        import traceback

        print(
            "BROKER_CHECK_FAILURE="
            + json.dumps(
                {
                    "type": type(error).__name__,
                    "stack": [
                        [Path(frame.filename).name, frame.name, frame.lineno]
                        for frame in traceback.extract_tb(error.__traceback__)
                    ],
                }
            ),
            file=sys.stderr,
        )
        sys.exit(1)
