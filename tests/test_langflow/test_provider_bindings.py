"""Request-principal and portable binding checks without native/provider requests."""

import asyncio
from contextlib import asynccontextmanager
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from langflow.services.auth.context import (
    AuthCredentialContext,
    get_current_auth_context,
    set_current_auth_context,
)
from laomedo.host.provider_connections.models import BrowserProviderSession
from laomedo.host.provider_connections.errors import ProviderConnectionError
from laomedo.integrations.langflow.provider_connections.bindings import (
    ProviderGraphBindings,
)
from laomedo.integrations.langflow.provider_connections.exports import (
    strip_local_bindings,
)


class ProviderBindingTests(unittest.IsolatedAsyncioTestCase):
    """Never let flow-owner context stand in for the actual signed-in browser."""

    @asynccontextmanager
    async def _failing_startup(self, app):
        self.assertIs(ProviderGraphBindings.service, app.state.provider_connections)
        raise RuntimeError("startup failed")
        yield  # pragma: no cover

    async def test_startup_exposes_service_to_catalogue_and_cleans_failed_startup(self):
        from laomedo.integrations.langflow.local_profiles.runtime import (
            LocalProfileRuntime,
        )

        service = Mock(controllers=None)
        app = SimpleNamespace(state=SimpleNamespace(provider_connections=service))
        runtime = object.__new__(LocalProfileRuntime)
        runtime._upstream_lifespan = self._failing_startup
        with patch.object(ProviderGraphBindings, "service", None):
            with self.assertRaisesRegex(RuntimeError, "startup failed"):
                async with runtime.lifespan(app):
                    self.fail("failed startup must not yield")
            self.assertIsNone(ProviderGraphBindings.service)
        service.close.assert_called_once_with()

    def setUp(self):
        self.profile = uuid4()
        service = Mock()
        service.revoked_leases = set()
        ProviderGraphBindings.install(service)
        self.addCleanup(ProviderGraphBindings.release, service)
        previous = get_current_auth_context()
        self.addCleanup(set_current_auth_context, previous)
        set_current_auth_context(AuthCredentialContext(method="jwt"))

    async def test_verified_browser_context_survives_worker_thread_but_not_foreign_flow(
        self,
    ):
        context = ProviderGraphBindings.session.set(
            BrowserProviderSession(profile_id=self.profile, lease_hash="browser")
        )
        try:
            self.assertEqual(
                await asyncio.to_thread(
                    ProviderGraphBindings.owner, SimpleNamespace(user_id=self.profile)
                ),
                self.profile,
            )
            with self.assertRaisesRegex(
                ProviderConnectionError, "provider_session_required"
            ):
                ProviderGraphBindings.owner(SimpleNamespace(user_id=uuid4()))
            ProviderGraphBindings.service.revoked_leases.add("browser")
            with self.assertRaisesRegex(
                ProviderConnectionError, "provider_session_required"
            ):
                ProviderGraphBindings.owner(SimpleNamespace(user_id=self.profile))
        finally:
            ProviderGraphBindings.session.reset(context)

    async def test_anonymous_and_api_context_cannot_borrow_even_with_known_local_selector(
        self,
    ):
        context = ProviderGraphBindings.session.set(
            BrowserProviderSession(profile_id=self.profile, lease_hash="browser")
        )
        try:
            for authentication in (None, AuthCredentialContext(method="api_key")):
                set_current_auth_context(authentication)
                with self.assertRaisesRegex(
                    ProviderConnectionError, "provider_session_required"
                ):
                    ProviderGraphBindings.owner(SimpleNamespace(user_id=self.profile))
        finally:
            ProviderGraphBindings.session.reset(context)

    async def test_export_and_import_clear_only_local_selector_and_its_account_options(
        self,
    ):
        field = {
            "value": str(uuid4()),
            "options": ["local-id"],
            "options_metadata": [{"display_name": "Local account"}],
            "show": True,
        }
        original = {
            "flows": [
                {
                    "data": {
                        "nodes": [
                            {
                                "data": {
                                    "node": {
                                        "template": {
                                            "provider_connection": field,
                                            "task": {"value": "Do work"},
                                        }
                                    }
                                }
                            }
                        ]
                    }
                }
            ]
        }
        portable = strip_local_bindings(original)
        template = portable["flows"][0]["data"]["nodes"][0]["data"]["node"]["template"]
        self.assertEqual(
            template["provider_connection"],
            {"value": "", "options": [], "options_metadata": [], "show": True},
        )
        self.assertEqual(template["task"], {"value": "Do work"})
        self.assertNotEqual(field["value"], "")
