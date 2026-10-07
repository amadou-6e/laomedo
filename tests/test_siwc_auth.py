"""Synthetic tests of the app-owned connection and rotating-token boundary."""

import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from io import BytesIO
from http.client import BadStatusLine
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from laomedo.siwc_auth import (AuthError, ChatGPTConnection, NEEDED,
                               _https_json, _verify_id_token)


class ChatGPTConnectionTests(unittest.TestCase):
    def test_exchange_diagnostic_reports_only_safe_status(self):
        private_text = "secret-code-and-token"
        error = HTTPError("https://auth.openai.com/private/" + private_text,
                          400, private_text, {}, BytesIO(private_text.encode()))
        with patch("laomedo.siwc_auth.build_opener") as opener:
            opener.return_value.open.side_effect = error
            with self.assertRaisesRegex(AuthError, "^auth_http_400$") as raised:
                _https_json("https://auth.openai.com/api/accounts/oauth/token",
                            fields={"code": private_text})
        self.assertNotIn(private_text, str(raised.exception))
        self.assertTrue(raised.exception.__suppress_context__)
        self.assertTrue(error.fp.closed)
        with patch("laomedo.siwc_auth.build_opener") as opener:
            opener.return_value.open.side_effect = URLError(private_text)
            with self.assertRaisesRegex(AuthError, "^auth_transport_failed$") as raised:
                _https_json("https://auth.openai.com/api/accounts/oauth/token",
                            fields={"code": private_text})
        self.assertNotIn(private_text, str(raised.exception))
        with patch("laomedo.siwc_auth.build_opener") as opener:
            opener.return_value.open.side_effect = URLError(
                ssl.SSLCertVerificationError(private_text))
            with self.assertRaisesRegex(AuthError, "^auth_tls_verify_failed$") as raised:
                _https_json("https://auth.openai.com/api/accounts/oauth/token",
                            fields={"code": private_text})
        self.assertNotIn(private_text, str(raised.exception))
        with patch("laomedo.siwc_auth.build_opener") as opener:
            opener.return_value.open.side_effect = BadStatusLine(private_text)
            with self.assertRaisesRegex(AuthError, "^auth_exchange_failed$") as raised:
                _https_json("https://auth.openai.com/api/accounts/oauth/token",
                            fields={"code": private_text})
        self.assertNotIn(private_text, str(raised.exception))

    def test_failed_exchange_does_not_connect_account(self):
        attempt = self.store.begin("http://127.0.0.1:1455/auth/callback")
        with self.assertRaisesRegex(AuthError, "^auth_tls_verify_failed$"):
            self.store.finish(attempt, {"code": "synthetic-code",
                "state": attempt["state"], "client_id": "oaiapp_fixture"},
                exchange=lambda *_args, **_kwargs:
                    (_ for _ in ()).throw(AuthError("auth_tls_verify_failed")))
        with self.assertRaisesRegex(AuthError, "auth_account_missing"):
            self.store.active()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "auth"
        self.store = ChatGPTConnection(self.root)
        self.scopes = " ".join(sorted(NEEDED | {"profile", "email"}))

    def _connect(self, *, client_id="oaiapp_fixture", subject="subject-a",
                 token="synthetic-access", expiry=3600):
        attempt = self.store.begin("http://127.0.0.1:1455/auth/callback",
                                   client_id=client_id if self._known(client_id)
                                   else None)
        callback = {"code": "synthetic-code", "state": attempt["state"],
                    "client_id": client_id}
        return self.store.finish(attempt, callback,
            exchange=lambda _url, fields: {
                "id_token": "synthetic-id", "access_token": token,
                "refresh_token": "synthetic-refresh", "scope": self.scopes,
                "expires_in": expiry},
            verify=lambda _token, _client, _nonce: {
                "iss": "https://auth.openai.com", "sub": subject})

    def _known(self, client_id):
        try:
            self.store._account(client_id)
            return True
        except AuthError:
            return False

    def test_registration_restart_and_private_summary(self):
        attempt = self.store.begin("http://127.0.0.1:1455/auth/callback")
        query = parse_qs(urlsplit(attempt["url"]).query)
        self.assertEqual(query["client_id"], ["dynamic_agent_client"])
        self.assertEqual(query["ext_agent_host_id"], [self.store.host_id])
        self.assertIn("chatgpt.tokens.use.direct", query["scope"][0])
        self.assertNotIn("synthetic-access", json.dumps(attempt))
        summary = self.store.finish(attempt, {"code": "code",
            "state": attempt["state"], "client_id": "oaiapp_fixture"},
            exchange=lambda _url, fields: {
                "id_token": "synthetic-id", "access_token": "synthetic-access",
                "refresh_token": "synthetic-refresh", "scope": self.scopes,
                "expires_in": 3600},
            verify=lambda _token, _client, _nonce: {
                "iss": "https://auth.openai.com", "sub": "subject-a"})
        self.assertNotIn("synthetic-access", json.dumps(summary))
        self.assertNotIn("synthetic-refresh", json.dumps(summary))
        restarted = ChatGPTConnection(self.root)
        self.assertEqual(restarted.host_id, self.store.host_id)
        token, again = restarted.access_token()
        self.assertEqual(token, "synthetic-access")
        self.assertEqual(again, summary)
        self.assertEqual(list(self.root.rglob("*.pending-*")), [])

    def test_id_token_signature_audience_issuer_and_nonce(self):
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        claims = {"iss": "https://auth.openai.com", "aud": "oaiapp_fixture",
                  "sub": "account-subject", "nonce": "fresh-nonce",
                  "exp": int(time.time()) + 600}
        token = jwt.encode(claims, private, algorithm="RS256",
                           headers={"kid": "fixture"})
        with patch("laomedo.siwc_auth._https_json", return_value={
                "jwks_uri": "https://auth.openai.com/.well-known/jwks.json"}), \
                patch("laomedo.siwc_auth.jwt.PyJWKClient") as client:
            client.return_value.get_signing_key_from_jwt.return_value.key = private.public_key()
            self.assertEqual(_verify_id_token(token, "oaiapp_fixture",
                                              "fresh-nonce")["sub"],
                             "account-subject")
            for audience, nonce in (("other-client", "fresh-nonce"),
                                    ("oaiapp_fixture", "wrong-nonce")):
                with self.subTest(audience=audience, nonce=nonce):
                    with self.assertRaisesRegex(AuthError, "auth_identity_invalid"):
                        _verify_id_token(token, audience, nonce)

    def test_wrong_state_scope_and_account_refuse_without_replacement(self):
        self._connect()
        attempt = self.store.begin("http://127.0.0.1:1455/auth/callback",
                                   client_id="oaiapp_fixture")
        with self.assertRaisesRegex(AuthError, "auth_state_mismatch"):
            self.store.finish(attempt, {"state": "wrong", "code": "code"})
        with self.assertRaisesRegex(AuthError, "auth_scope_missing"):
            self.store.finish(attempt, {"state": attempt["state"],
                "code": "code"}, exchange=lambda *_args, **_kwargs: {
                    "id_token": "id", "access_token": "other",
                    "refresh_token": "refresh", "scope": "openid",
                    "expires_in": 3600},
                verify=lambda *_args: {"iss": "https://auth.openai.com",
                                       "sub": "subject-a"})
        with self.assertRaisesRegex(AuthError, "auth_account_mismatch"):
            self.store.finish(attempt, {"state": attempt["state"],
                "code": "code"}, exchange=lambda *_args, **_kwargs: {
                    "id_token": "id", "access_token": "other",
                    "refresh_token": "refresh", "scope": self.scopes,
                    "expires_in": 3600},
                verify=lambda *_args: {"iss": "https://auth.openai.com",
                                       "sub": "subject-b"})
        self.assertEqual(self.store.access_token()[0], "synthetic-access")

    def test_serial_refresh_and_ambiguous_response_refuses_reuse(self):
        self._connect(expiry=60)
        calls = []
        results = []

        def refresh(_url, fields):
            calls.append(fields["refresh_token"])
            time.sleep(.03)
            return {"access_token": "replacement-access",
                    "refresh_token": "replacement-refresh",
                    "expires_in": 3600}

        threads = [threading.Thread(target=lambda: results.append(
            self.store.access_token(refresh=refresh)[0])) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(calls, ["synthetic-refresh"])
        self.assertEqual(results, ["replacement-access"] * 2)
        account = self.store.active()
        self.assertEqual(account["refresh_token"], "replacement-refresh")
        self.assertEqual(account["generation"], 2)
        account["expires_at"] = time.time() - 1
        from laomedo.siwc_auth import _atomic_private
        _atomic_private(self.store._path(account["client_id"]), account)
        with self.assertRaisesRegex(AuthError, "auth_refresh_unknown"):
            self.store.access_token(refresh=lambda *_args, **_kwargs:
                                    (_ for _ in ()).throw(TimeoutError()))
        with self.assertRaisesRegex(AuthError, "auth_refresh_unknown"):
            self.store.access_token(refresh=refresh)
        self.assertEqual(calls, ["synthetic-refresh"])

    def test_malformed_successful_refresh_is_not_retried(self):
        self._connect(expiry=60)
        attempts = []

        def malformed(_url, fields):
            attempts.append(fields["refresh_token"])
            return {"access_token": "rotated-access",
                    "refresh_token": "rotated-refresh",
                    "expires_in": 3600, "scope": "openid"}

        with self.assertRaisesRegex(AuthError, "auth_refresh_unknown"):
            self.store.access_token(refresh=malformed)
        self.assertEqual(self.store.active()["state"], "refresh_unknown")
        with self.assertRaisesRegex(AuthError, "auth_refresh_unknown"):
            self.store.access_token(refresh=malformed)
        self.assertEqual(attempts, ["synthetic-refresh"])

    def test_dynamic_registration_cannot_replace_other_subject(self):
        self._connect(client_id="oaiapp_fixture", subject="first")
        attempt = self.store.begin("http://127.0.0.1:1455/auth/callback")
        with self.assertRaisesRegex(AuthError, "auth_account_mismatch"):
            self.store.finish(attempt, {"code": "code", "state": attempt["state"],
                "client_id": "oaiapp_fixture"},
                exchange=lambda _url, fields: {
                    "id_token": "new-id", "access_token": "new-access",
                    "refresh_token": "new-refresh", "scope": self.scopes,
                    "expires_in": 3600},
                verify=lambda *_args: {"iss": "https://auth.openai.com",
                                       "sub": "different"})
        self.assertEqual(self.store.active()["subject"], "first")

    def test_switch_and_sign_out_clear_only_selected_account(self):
        self._connect(client_id="oaiapp_one", subject="one", token="first")
        self._connect(client_id="oaiapp_two", subject="two", token="second")
        self.assertEqual(self.store.access_token()[0], "second")
        self.store.switch("oaiapp_one")
        self.assertEqual(self.store.access_token()[0], "first")
        seen = []
        def revoke(token, client):
            with self.assertRaisesRegex(AuthError, "auth_account_missing"):
                self.store.active()
            seen.append((token, client))
            return True

        outcome = self.store.sign_out(revoke=revoke)
        self.assertTrue(outcome["remote_revocation_confirmed"])
        self.assertEqual(seen, [("synthetic-refresh", "oaiapp_one")])
        with self.assertRaisesRegex(AuthError, "auth_account_missing"):
            self.store.active()
        self.store.switch("oaiapp_two")
        self.assertEqual(self.store.access_token()[0], "second")


if __name__ == "__main__":
    unittest.main()
