"""Untrusted per-profile native API; no broker authority or reusable credentials."""

from contextlib import asynccontextmanager
import os
import secrets

from fastapi import HTTPException


class NativeProfileRuntime:
    """Serve one isolated operational identity behind trusted host admission.

    This runtime is deliberately untrusted. Its local user records are never
    profile authentication proof. Host deployment must enforce a network-free
    container with only this owner's operational state, not broker state.
    """

    def __init__(self, settings):
        """Retain only explicit operational owner/storage settings."""
        self.settings = settings
        self._native_lifespan = None

    def create_app(self):
        """Construct native APIs in the container, never in the credential broker."""
        if os.name != "posix" or os.getuid() != 65532:
            raise RuntimeError("graph_runtime_container_required")
        root = self.settings.state_root
        root.mkdir(parents=True, exist_ok=True)
        os.environ.update(
            {
                "LANGFLOW_CONFIG_DIR": str(root),
                "LFX_CONFIG_DIR": str(root),
                "LANGFLOW_DATABASE_URL": "sqlite:///" + (root / "graphs.db").as_posix(),
                "LANGFLOW_AUTO_LOGIN": "false",
                # Native startup requires its own bootstrap account even though
                # API requests use the ordinary operational owner below. This
                # random container-local password is never a broker profile PIN.
                "LANGFLOW_SUPERUSER": "graph-bootstrap",
                "LANGFLOW_SUPERUSER_PASSWORD": secrets.token_urlsafe(48),
                "LANGFLOW_DO_NOT_TRACK": "true",
            }
        )
        # Native imports can initialize settings. Set the container's explicit
        # store before importing any native services or application module.
        from langflow.main import create_app
        from langflow.services.auth.utils import get_current_user

        app = create_app()
        self._native_lifespan = app.router.lifespan_context
        app.router.lifespan_context = self.lifespan
        app.dependency_overrides[get_current_user] = self.current_user
        return app

    @asynccontextmanager
    async def lifespan(self, app):
        """Initialize only this operational database and its ordinary native user."""
        from langflow.initial_setup.setup import get_or_create_default_folder
        from langflow.services.auth.utils import get_password_hash
        from langflow.services.database.models.user.model import User
        from lfx.services.deps import session_scope

        async with self._native_lifespan(app):
            async with session_scope() as session:
                user = await session.get(User, self.settings.owner_id)
                if user is None:
                    user = User(
                        id=self.settings.owner_id,
                        username=str(self.settings.owner_id),
                        password=get_password_hash(secrets.token_urlsafe(32)),
                        is_active=True,
                        is_superuser=False,
                    )
                    session.add(user)
                    await session.flush()
                await get_or_create_default_folder(session, self.settings.owner_id)
            yield

    async def current_user(self):
        """Resolve only this container's fixed operational user, without a browser JWT.

        This dependency override is safe only behind the isolated private
        transport. It must never replace the broker's real profile admission.
        """
        from langflow.services.database.models.user.model import User
        from lfx.services.deps import session_scope

        async with session_scope() as session:
            user = await session.get(User, self.settings.owner_id)
            if user is None or not user.is_active or user.is_superuser:
                raise HTTPException(
                    status_code=403, detail="Graph workspace unavailable"
                )
            return User.model_validate(user.model_dump())
