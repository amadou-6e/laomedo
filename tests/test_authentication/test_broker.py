"""Trusted broker route/startup boundaries; not process or live GitHub acceptance."""

from importlib.util import find_spec
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

if find_spec("langflow") is None:
    raise unittest.SkipTest("Optional Langflow runtime is not installed")

from httpx import ASGITransport, AsyncClient

from laomedo.integrations.langflow.authentication.broker import PrivateBrokerRuntime
from laomedo.integrations.langflow.authentication.settings import PrivateBrowserSettings
from laomedo.integrations.langflow.local_profiles.runtime import LocalProfileRuntime


class PrivateBrokerRuntimeTests(unittest.IsolatedAsyncioTestCase):
    """No graph or component-evaluation routes belong in the vault-owning app."""

    def setUp(self):
        self.profile = Mock(spec=LocalProfileRuntime)
        private = patch(
            "laomedo.integrations.langflow.authentication.broker.PrivateBrowserRuntime",
            autospec=True,
        )
        self.private_class = private.start()
        self.addCleanup(private.stop)
        limiter = patch(
            "laomedo.integrations.langflow.authentication.broker.get_rate_limiter"
        )
        limiter.start()
        self.addCleanup(limiter.stop)
        self.runtime = PrivateBrokerRuntime(
            self.profile,
            PrivateBrowserSettings(
                origin="http://127.0.0.1:17867",
                runtime_root=Path(tempfile.gettempdir()) / "broker-test-not-created",
            ),
        )
        self.app = self.runtime.create_app()

    def test_factory_installs_only_identity_routes_before_owned_runtime_adapters(self):
        self.profile.configure.assert_called_once_with(self.app)
        self.private_class.return_value.configure.assert_called_once_with(self.app)
        paths = set()
        pending = list(self.app.routes)
        while pending:
            route = pending.pop()
            candidates = getattr(route, "effective_candidates", None)
            if candidates is not None:
                pending.extend(candidates())
            else:
                paths.add(route.path)
        self.assertEqual(
            paths,
            {
                "/api/v1/login",
                "/api/v1/refresh",
                "/api/v1/session",
                "/api/v1/logout",
                "/api/v1/users/whoami",
                "/api/v1/laomedo/profile-mode",
            },
        )

    async def test_native_execution_and_component_editing_are_not_host_endpoints(self):
        async with AsyncClient(
            transport=ASGITransport(app=self.app), base_url="http://127.0.0.1:17867"
        ) as client:
            for path in (
                "/api/v2/workflows",
                "/api/v1/build/test/flow",
                "/api/v1/custom_component",
                "/api/v1/custom_component/update",
                "/api/v1/validate/code",
                "/api/v1/mcp/servers",
            ):
                response = await client.post(path, json={"code": "not executed"})
                self.assertEqual(response.status_code, 404, path)

    async def test_lifespan_initializes_only_explicit_trusted_services(self):
        with (
            patch(
                "laomedo.integrations.langflow.authentication.broker.initialize_services",
                new_callable=AsyncMock,
            ) as initialize,
            patch(
                "laomedo.integrations.langflow.authentication.broker.teardown_services",
                new_callable=AsyncMock,
            ) as teardown,
        ):
            async with self.runtime.lifespan(self.app):
                initialize.assert_awaited_once_with()
                teardown.assert_not_awaited()
            teardown.assert_awaited_once_with()

    async def test_failed_initialization_does_not_enter_or_mutate_through_teardown(
        self,
    ):
        with (
            patch(
                "laomedo.integrations.langflow.authentication.broker.initialize_services",
                new_callable=AsyncMock,
                side_effect=RuntimeError("synthetic startup failure"),
            ),
            patch(
                "laomedo.integrations.langflow.authentication.broker.teardown_services",
                new_callable=AsyncMock,
            ) as teardown,
        ):
            with self.assertRaises(RuntimeError):
                async with self.runtime.lifespan(self.app):
                    self.fail("failed initialization entered the serving state")
            teardown.assert_not_awaited()
