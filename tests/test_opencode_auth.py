"""Synthetic Console credential resolution; no real tokens or network calls."""
import sqlite3
from contextlib import closing
import tempfile
import time
import unittest
from pathlib import Path

from laomedo.opencode_auth import console_provider, credential, NoRedirect


class ConsoleAuthTests(unittest.TestCase):
    def test_redacted_and_placeholder_values_rejected(self):
        for value in ("[REDACTED]", "********", "{env:KEY}", "CANARY-fixture", "", None):
            with self.assertRaises(ValueError):
                credential(value)

    def test_active_account_only_no_refresh_or_database_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "opencode.db"
            with closing(sqlite3.connect(path)) as db:
                db.execute("create table account(id text, access_token text, token_expiry integer, url text)")
                db.execute("create table account_state(active_account_id text, active_org_id text)")
                db.execute("insert into account values(?,?,?,?)", (
                    "fixture", "synthetic-access", int(time.time()*1000)+600000, "https://opencode.ai/console"))
                db.execute("insert into account_state values('fixture','synthetic-org')")
                db.commit()
            before = path.read_bytes()
            def fetch(url, headers):
                self.assertEqual(url, "https://opencode.ai/console/api/config")
                self.assertEqual(headers["Authorization"], "Bearer synthetic-access")
                return {"config": {"provider": {"opencode-go": {
                    "api": "https://opencode.ai/inference/go/openai/v1", "npm": "@ai-sdk/openai-compatible",
                    "models": {"gpt-6-luna": {"provider": {"npm": "@ai-sdk/openai"}}}, "options": {
                    "apiKey": "{env:OPENCODE_CONSOLE_TOKEN}",
                    "headers": {"x-opencode-org-id": "synthetic-org"}}}}}}
            selected, org = console_provider(path, fetch=fetch)
            self.assertEqual(selected, {"type": "api", "key": "synthetic-access"})
            self.assertEqual(org, "synthetic-org")
            self.assertEqual(path.read_bytes(), before)
            _, _, routing = console_provider(path, fetch=fetch, include_routing=True)
            self.assertEqual(routing["models"]["gpt-6-luna"]["provider"]["npm"], "@ai-sdk/openai")
            _, _, _, validity = console_provider(path, fetch=fetch, include_routing=True,
                                                   include_expiry=True)
            self.assertEqual(validity["credential_mode"], "console_token")
            self.assertGreater(validity["expires_at_ms"], int(time.time() * 1000))
            with closing(sqlite3.connect(path)) as db:
                db.execute("update account set url='https://untrusted.invalid'")
                db.commit()
            with self.assertRaisesRegex(ValueError, "origin_not_allowed"):
                console_provider(path, fetch=fetch)

    def test_redirect_never_forwards_account_token(self):
        with self.assertRaisesRegex(ValueError, "redirect_rejected"):
            NoRedirect().redirect_request(None, None, None, None, None, None)

    def test_expiry_org_and_model_route_rejections(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'opencode.db'
            with closing(sqlite3.connect(path)) as db:
                db.execute('create table account(id text, access_token text, token_expiry integer, url text)')
                db.execute('create table account_state(active_account_id text, active_org_id text)')
                db.execute('insert into account values(?,?,?,?)',
                           ('fixture', 'synthetic-access', int(time.time() * 1000) + 30000,
                            'https://opencode.ai/console'))
                db.execute("insert into account_state values('fixture','synthetic-org')")
                db.commit()
            def provider(*, org='synthetic-org', sdk='@ai-sdk/openai',
                         endpoint='https://opencode.ai/inference/go/openai/v1'):
                return {'config': {'provider': {'opencode-go': {
                    'api': 'https://opencode.ai/inference/go/openai/v1',
                    'npm': '@ai-sdk/openai-compatible',
                    'models': {'gpt-6-luna': {'provider': {'npm': sdk, 'api': endpoint}}},
                    'options': {'apiKey': '{env:OPENCODE_CONSOLE_TOKEN}',
                                'headers': {'x-opencode-org-id': org}}}}}}
            with self.assertRaisesRegex(ValueError, 'token_refresh_required'):
                console_provider(path, fetch=lambda *_: provider(), include_routing=True)
            with closing(sqlite3.connect(path)) as db:
                db.execute('update account set token_expiry=?', (int(time.time() * 1000) + 600000,))
                db.commit()
            cases = [
                ({'org': 'other-org'}, 'organization_context_mismatch'),
                ({'endpoint': 'https://evil.invalid/inference/go/openai/v1'}, 'model_endpoint_not_allowed'),
                ({'sdk': '@ai-sdk/untrusted'}, 'model_sdk_not_allowed'),
            ]
            for change, expected in cases:
                with self.subTest(change=change), self.assertRaisesRegex(ValueError, expected):
                    console_provider(path, fetch=lambda *_args, **_kwargs: provider(**change),
                                     include_routing=True)
