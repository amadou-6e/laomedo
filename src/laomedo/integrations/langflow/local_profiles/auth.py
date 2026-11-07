"""Refuse the internal startup actor while preserving upstream profile auth."""

from uuid import UUID

from fastapi import HTTPException
from langflow.services.auth.exceptions import InvalidCredentialsError
from langflow.services.auth.service import AuthService
from langflow.services.database.models.user.crud import get_user_by_id

from laomedo.integrations.langflow.local_profiles.settings import SYSTEM_PROFILE_NAME


class LocalProfileAuthService(AuthService):
    """Profile-mode guard, installed after upstream service initialization.

    This is not a standalone security boundary: startup must also refuse internal
    API keys and environment/external authentication. Some upstream API-key paths
    use the database credential helper directly rather than this service.
    """

    @staticmethod
    def _is_profile(user) -> bool:
        return (
            user is not None
            and user.is_active
            and not user.is_superuser
            and user.username.casefold() != SYSTEM_PROFILE_NAME.casefold()
        )

    async def authenticate_user(self, username, password, db, request=None):
        """Refuse the internal name without testing its startup password."""
        if username.casefold() == SYSTEM_PROFILE_NAME.casefold():
            return None
        user = await super().authenticate_user(username, password, db, request)
        return user if self._is_profile(user) else None

    async def create_user_tokens(
        self, user_id: UUID, db, *, update_last_login: bool = False
    ) -> dict:
        """Cover login and inherited refresh; never mint system-actor tokens."""
        user = await get_user_by_id(db, user_id)
        if not self._is_profile(user):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return await super().create_user_tokens(
            user_id, db, update_last_login=update_last_login
        )

    async def _authenticate_with_token(self, token, db):
        """Check the principal after upstream token validation and expiry checks."""
        user = await super()._authenticate_with_token(token, db)
        if not self._is_profile(user):
            raise InvalidCredentialsError()
        return user

    async def _authenticate_with_api_key(self, api_key):
        """Defensive service-path guard; direct API-key callers need admission."""
        user = await super()._authenticate_with_api_key(api_key)
        if not self._is_profile(user):
            raise InvalidCredentialsError()
        return user
