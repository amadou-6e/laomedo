"""Local profile registration delegates the upstream identity transaction."""

import asyncio

from fastapi import HTTPException
from langflow.api.v1.users import add_user
from langflow.services.database.models.user.model import User, UserCreate
from langflow.services.deps import session_scope
from sqlmodel import select

from laomedo.integrations.langflow.local_profiles.errors import ProfileError
from laomedo.integrations.langflow.local_profiles.models import ProfileCreateRequest
from laomedo.integrations.langflow.local_profiles.models import ProfileIndex
from laomedo.integrations.langflow.local_profiles.models import ProfileSummary
from laomedo.integrations.langflow.local_profiles.settings import SYSTEM_PROFILE_NAME


class LocalProfileRegistry:
    """Single-process registration boundary; no credential or session store.

    The loopback runtime has one worker. Its creation lock spans uniqueness
    admission and the upstream committed transaction. Generic signup and direct
    identity mutation remain unavailable, preventing bypass of this policy.
    """

    def __init__(self):
        self._creation_lock = asyncio.Lock()

    async def list_profiles(self) -> ProfileIndex:
        """Project only active ordinary identities, excluding the reserved name."""
        try:
            async with session_scope() as db:
                users = (
                    await db.exec(
                        select(User).where(
                            User.is_active == True, User.is_superuser == False
                        )
                    )
                ).all()
                return ProfileIndex(
                    profiles=tuple(
                        ProfileSummary(id=user.id, name=user.username)
                        for user in sorted(
                            users, key=lambda item: item.username.casefold()
                        )
                        if user.username.casefold() != SYSTEM_PROFILE_NAME.casefold()
                    )
                )
        except Exception:
            raise ProfileError("profile_list_unavailable") from None

    async def create_profile(self, request: ProfileCreateRequest) -> ProfileSummary:
        """Delegate once; uncertain outcomes must be reconciled, never replayed."""
        async with self._creation_lock:
            try:
                async with session_scope() as db:
                    users = (await db.exec(select(User))).all()
                    if any(
                        user.username.casefold() == request.name.casefold()
                        for user in users
                    ):
                        raise ProfileError("profile_name_unavailable")
                    actor = next(
                        (
                            user
                            for user in users
                            if user.username == SYSTEM_PROFILE_NAME
                        ),
                        None,
                    )
                    if actor is None or not actor.is_superuser or not actor.is_active:
                        raise ProfileError("profile_setup_unavailable")
                    created = await add_user(
                        user=UserCreate(
                            username=request.name,
                            password=request.pin.get_secret_value(),
                        ),
                        session=db,
                        current_user=actor,
                    )
                    if created.is_superuser or not created.is_active:
                        raise ProfileError("profile_creation_unconfirmed")
                    return ProfileSummary(id=created.id, name=created.username)
            except ProfileError:
                raise
            except HTTPException as error:
                if (
                    error.status_code == 400
                    and error.detail == "This username is unavailable."
                ):
                    raise ProfileError("profile_name_unavailable") from None
                raise ProfileError("profile_creation_unconfirmed") from None
            except Exception:
                raise ProfileError("profile_creation_unconfirmed") from None
