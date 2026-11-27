"""Synthetic custody/OAuth fixtures; no host authentication or provider acceptance."""

from urllib.parse import urlencode
from uuid import uuid4

from pydantic import SecretStr

from laomedo.github.connections.errors import GitHubOAuthError
from laomedo.github.connections.models import (
    GitHubConnectionCredential,
    GitHubOAuthAttempt,
)
from laomedo.host.credentials.github.errors import GitHubVaultError


class ConnectionVaultFixture:
    """In-memory synthetic targets, including ambiguous write and deletion failures."""

    def __init__(self):
        self.values = {}
        self.fail_store = False
        self.fail_remove = False
        self.before_remove = None

    def store(self, reference, value):
        self.values[reference] = value
        if self.fail_store:
            raise GitHubVaultError()

    def load(self, reference):
        return self.values.get(reference)

    def remove(self, reference):
        if self.before_remove:
            self.before_remove(reference)
        if self.fail_remove:
            raise GitHubVaultError()
        self.values.pop(reference, None)


class ConnectionOAuthFixture:
    """Count synthetic one-use exchanges; actual Authlib mechanics have other controls."""

    def __init__(self, factory, settings):
        self.factory, self.settings = factory, settings

    async def begin(self):
        state = uuid4().hex + uuid4().hex
        return GitHubOAuthAttempt(
            state=SecretStr(state),
            verifier=SecretStr("v" * 64),
            authorization_url="https://github.com/login/oauth/authorize?"
            + urlencode({"state": state}),
        )

    async def complete(self, attempt, callback):
        self.factory.exchanges += 1
        return self.factory.credential()

    async def refresh(self, credential):
        self.factory.refreshes += 1
        if self.factory.fail_refresh:
            raise GitHubOAuthError()
        return self.factory.credential()


class ConnectionOAuthFactory:
    """Provide finite synthetic expiring credentials and observable exchange counts."""

    def __init__(self):
        self.exchanges = 0
        self.refreshes = 0
        self.fail_refresh = False

    def __call__(self, settings):
        return ConnectionOAuthFixture(self, settings)

    def credential(self):
        return GitHubConnectionCredential.from_oauth(
            {
                "access_token": "synthetic-access",
                "refresh_token": "synthetic-refresh-" + uuid4().hex,
                "token_type": "bearer",
                "expires_in": 3600,
                "refresh_token_expires_in": 7200,
            },
            1000.0,
        )
