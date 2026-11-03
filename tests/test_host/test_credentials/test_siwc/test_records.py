"""Preserve serialized contracts, authority boundaries and unknown outcomes."""

from support.paths import repository_root
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
from pydantic import ValidationError
from laomedo.host.credentials.siwc.connection import ChatGPTConnection
from laomedo.host.credentials.siwc.models import (
    OAuthAccount,
    OAuthAttempt,
    OAuthAuthorizationRequest,
    OAuthCodeExchange,
)
from laomedo.host.credentials.siwc.settings import AUTH_ORIGIN, RESOURCE, SCOPES


class OAuthRecordTests(unittest.TestCase):
    def assert_secret_output_excluded(self, model, secrets):
        for rendered in (
            repr(model),
            str(model),
            str(model.model_dump()),
            model.model_dump_json(),
        ):
            for secret in secrets:
                self.assertNotIn(secret, rendered)

    def test_oauth_authorization_query_preserves_order_and_optional_hints(self):
        base = dict(
            client_id="oaiapp_client",
            ext_agent_host_id="urn:uuid:host",
            redirect_uri="http://127.0.0.1:9000/auth/callback",
            scope="scope a",
            resource="https://resource.example",
            state="private-state",
            nonce="private-nonce",
            code_challenge="challenge",
        )
        for hints in (
            {},
            {"agent_name_hint": "Laomedo"},
            {"id_token_hint": "private-id-token", "login_hint": "private-email"},
            {
                "id_token_hint": {"legacy": "private-id-token"},
                "login_hint": ["private-email"],
            },
        ):
            with self.subTest(hints=list(hints)):
                request = OAuthAuthorizationRequest(**base, **hints)
                expected = dict(
                    client_id=base["client_id"],
                    ext_agent_host_id=base["ext_agent_host_id"],
                    response_type="code",
                    redirect_uri=base["redirect_uri"],
                    scope=base["scope"],
                    resource=base["resource"],
                    state=base["state"],
                    nonce=base["nonce"],
                    code_challenge_method="S256",
                    code_challenge=base["code_challenge"],
                    **hints,
                )
                self.assertEqual(request.to_query(), urlencode(expected))
                self.assert_secret_output_excluded(
                    request,
                    (
                        "private-state",
                        "private-nonce",
                        "private-id-token",
                        "private-email",
                    ),
                )

    def test_begin_preserves_private_attempt_and_legacy_account_hints(self):
        # Bypass filesystem/account enrollment; only this existing writer is tested.
        connection = object.__new__(ChatGPTConnection)
        connection.host_id = "urn:uuid:host"
        redirect = "http://127.0.0.1:9000/auth/callback"
        for account in (
            None,
            {
                "subject": "private-subject",
                "email": ["private-email"],
                "id_token": {"old": "private-token"},
            },
        ):
            client = None if account is None else "oaiapp_client"
            with (
                self.subTest(existing=account is not None),
                patch.object(connection, "_account", return_value=account),
                patch(
                    "laomedo.host.credentials.siwc.connection.secrets.token_urlsafe",
                    side_effect=["verifier", "state", "nonce"],
                ),
            ):
                attempt = connection.begin(redirect, client_id=client)
            self.assertEqual(
                list(attempt),
                [
                    "url",
                    "state",
                    "nonce",
                    "verifier",
                    "redirect_uri",
                    "client_id",
                    "previous_subject",
                ],
            )
            self.assertEqual(
                {key: value for key, value in attempt.items() if key != "url"},
                dict(
                    state="state",
                    nonce="nonce",
                    verifier="verifier",
                    redirect_uri=redirect,
                    client_id=client,
                    previous_subject=account["subject"] if account else None,
                ),
            )
            self.assertTrue(
                attempt["url"].startswith(AUTH_ORIGIN + "/api/accounts/authorize?")
            )
            self.assertIn(
                urlencode({"scope": SCOPES, "resource": RESOURCE}), attempt["url"]
            )
            self.assertIn(
                "id_token_hint=" if account else "agent_name_hint=Laomedo",
                attempt["url"],
            )

    def test_oauth_private_projections_and_safe_exception_text(self):
        attempt_values = dict(
            url="private-url",
            state="private-state",
            nonce="private-nonce",
            verifier="private-verifier",
            redirect_uri="http://callback",
            client_id=None,
            previous_subject=None,
        )
        attempt = OAuthAttempt(**attempt_values)
        self.assertEqual(attempt.to_private_payload(), attempt_values)
        self.assert_secret_output_excluded(
            attempt,
            tuple(
                value
                for key, value in attempt_values.items()
                if key in {"url", "state", "nonce", "verifier"}
            ),
        )
        exchange = OAuthCodeExchange(
            client_id="client",
            code="private-code",
            code_verifier="private-verifier",
            redirect_uri="http://callback",
            resource="resource",
        )
        self.assertEqual(
            exchange.to_private_payload(),
            dict(
                grant_type="authorization_code",
                client_id="client",
                code="private-code",
                code_verifier="private-verifier",
                redirect_uri="http://callback",
                resource="resource",
            ),
        )
        self.assert_secret_output_excluded(
            exchange, ("private-code", "private-verifier")
        )
        values = dict(
            client_id="client",
            subject="private-subject",
            issuer="issuer",
            email={"legacy": "private-email"},
            ext_agent_host_id="host",
            id_token="private-id",
            access_token="private-access",
            refresh_token="private-refresh",
            scopes=["a", "b"],
            expires_at=300,
            generation=2.5,
            state="active",
        )
        account = OAuthAccount(**values)
        self.assertEqual(account.to_private_record(), values)
        self.assertEqual(list(account.to_private_record()), list(values))
        self.assertIs(type(account.to_private_record()["expires_at"]), int)
        self.assert_secret_output_excluded(
            account,
            (
                "private-subject",
                "private-email",
                "private-id",
                "private-access",
                "private-refresh",
            ),
        )
        with self.assertRaises(ValidationError) as raised:
            OAuthAccount(**{**values, "access_token": ["private-invalid-access"]})
        # Pydantic's errors()/json() include inputs by default. Only explicit safe
        # projections and exception text are appropriate for diagnostics.
        for rendered in (
            str(raised.exception),
            repr(raised.exception),
            str(raised.exception.errors(include_input=False)),
            raised.exception.json(include_input=False),
        ):
            self.assertNotIn("private-invalid-access", rendered)

    def test_legacy_host_identity_json_keeps_existing_query_encoding(self):
        from urllib.parse import parse_qs, urlencode

        for host_id in (None, 7, True, ["legacy"], {"legacy": "host"}):
            values = dict(
                client_id="dynamic_agent_client",
                ext_agent_host_id=host_id,
                redirect_uri="http://127.0.0.1:1/auth/callback",
                scope="scope",
                resource="resource",
                state="private-state",
                nonce="private-nonce",
                code_challenge="challenge",
            )
            with self.subTest(identity_type=type(host_id).__name__):
                request = OAuthAuthorizationRequest(**values)
                expected = parse_qs(urlencode({"ext_agent_host_id": host_id}))
                self.assertEqual(
                    parse_qs(request.to_query())["ext_agent_host_id"],
                    expected["ext_agent_host_id"],
                )
                self.assertNotIn("ext_agent_host_id", request.model_dump())
