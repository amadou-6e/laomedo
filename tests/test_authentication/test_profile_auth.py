"""Internal auth-adapter regressions; no browser/profile acceptance claim."""

import unittest
from importlib.util import find_spec

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

if find_spec("langflow") is None:
    raise unittest.SkipTest("Optional Langflow runtime is not installed")

from fastapi import HTTPException
from langflow.services.auth.exceptions import (
    AuthenticationError,
    InvalidCredentialsError,
)
from langflow.services.auth.service import AuthService

from laomedo.integrations.langflow.local_profiles.auth import LocalProfileAuthService
from laomedo.integrations.langflow.local_profiles.settings import SYSTEM_PROFILE_NAME


class ProfileAuthTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.auth = object.__new__(LocalProfileAuthService)
        self.profile = SimpleNamespace(
            username="Work", is_active=True, is_superuser=False
        )
        self.system = SimpleNamespace(
            username=SYSTEM_PROFILE_NAME, is_active=True, is_superuser=True
        )

    async def test_internal_password_never_reaches_upstream_verification(self):
        with patch.object(
            AuthService, "authenticate_user", new_callable=AsyncMock
        ) as parent:
            self.assertIsNone(
                await self.auth.authenticate_user(
                    SYSTEM_PROFILE_NAME.upper(), "not-a-real-secret", None
                )
            )
            parent.assert_not_awaited()

    async def test_ordinary_authentication_delegates_without_changing_request(self):
        db, request = object(), object()
        with patch.object(
            AuthService,
            "authenticate_user",
            new_callable=AsyncMock,
            return_value=self.profile,
        ) as parent:
            self.assertIs(
                await self.auth.authenticate_user("Work", "001234", db, request),
                self.profile,
            )
            parent.assert_awaited_once_with("Work", "001234", db, request)

    async def test_missing_inactive_or_privileged_user_cannot_receive_tokens(self):
        for user in (
            None,
            self.system,
            SimpleNamespace(username="Other", is_active=False, is_superuser=False),
            SimpleNamespace(username="Other", is_active=True, is_superuser=True),
        ):
            with (
                self.subTest(user=user),
                patch(
                    "laomedo.integrations.langflow.local_profiles.auth.get_user_by_id",
                    new_callable=AsyncMock,
                    return_value=user,
                ),
                patch.object(
                    AuthService, "create_user_tokens", new_callable=AsyncMock
                ) as parent,
            ):
                with self.assertRaises(HTTPException) as error:
                    await self.auth.create_user_tokens(uuid4(), None)
                self.assertEqual(error.exception.status_code, 401)
                parent.assert_not_awaited()

    async def test_ordinary_token_creation_preserves_login_metadata_option(self):
        id, db = uuid4(), object()
        with (
            patch(
                "laomedo.integrations.langflow.local_profiles.auth.get_user_by_id",
                new_callable=AsyncMock,
                return_value=self.profile,
            ),
            patch.object(
                AuthService,
                "create_user_tokens",
                new_callable=AsyncMock,
                return_value={"upstream": "result"},
            ) as parent,
        ):
            self.assertEqual(
                await self.auth.create_user_tokens(id, db, update_last_login=True),
                {"upstream": "result"},
            )
            parent.assert_awaited_once_with(id, db, update_last_login=True)

    async def test_validated_system_tokens_and_api_keys_are_refused(self):
        with patch.object(
            AuthService,
            "_authenticate_with_token",
            new_callable=AsyncMock,
            return_value=self.system,
        ):
            with self.assertRaises(InvalidCredentialsError):
                await self.auth._authenticate_with_token("not-a-real-token", None)
        with patch.object(
            AuthService,
            "_authenticate_with_api_key",
            new_callable=AsyncMock,
            return_value=self.system,
        ):
            with self.assertRaises(InvalidCredentialsError):
                await self.auth._authenticate_with_api_key("not-a-real-key")


class ProfileUpstreamContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_registered_guard_survives_first_authentication_resolution(self):
        from langflow.services.deps import get_auth_service
        from lfx.services.manager import ServiceManager
        from lfx.services.schema import ServiceType

        manager = ServiceManager()
        manager._plugins_discovered = True
        manager.set_factory_registered()
        manager.services[ServiceType.SETTINGS_SERVICE] = SimpleNamespace()
        manager.register_service_class(
            ServiceType.AUTH_SERVICE, LocalProfileAuthService
        )
        with patch("lfx.services.manager._service_manager", manager):
            first = get_auth_service()
            self.assertIsInstance(first, LocalProfileAuthService)
            self.assertIsNone(
                await first.authenticate_user(
                    SYSTEM_PROFILE_NAME, "not-a-real-secret", None
                )
            )
            self.assertIs(get_auth_service(), first)

    async def test_inherited_websocket_sse_and_mcp_paths_reject_internal_token(self):
        auth = LocalProfileAuthService(
            SimpleNamespace(
                auth_settings=SimpleNamespace(
                    AUTO_LOGIN=False, EXTERNAL_AUTH_ENABLED=False
                )
            )
        )
        db = AsyncMock()
        with (
            patch.object(
                AuthService,
                "_authenticate_with_token",
                new_callable=AsyncMock,
                return_value=SimpleNamespace(
                    username=SYSTEM_PROFILE_NAME, is_active=True, is_superuser=True
                ),
            ),
            patch.object(
                auth, "_discard_failed_credential_state", new_callable=AsyncMock
            ),
        ):
            for method, args in (
                (auth.get_current_user_for_websocket, ("not-a-real-token", None, db)),
                (auth.get_current_user_for_sse, ("not-a-real-token", None, db)),
                (auth.get_current_user_mcp, ("not-a-real-token", None, None, db)),
            ):
                with (
                    self.subTest(method=method.__name__),
                    self.assertRaises((AuthenticationError, HTTPException)),
                ):
                    await method(*args)

    def test_profile_creation_signature_remains_the_pinned_upstream_contract(self):
        from inspect import signature
        from langflow.api.v1.users import add_user

        self.assertEqual(
            list(signature(add_user).parameters), ["user", "session", "current_user"]
        )
