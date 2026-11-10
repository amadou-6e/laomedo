"""Opt-in native private-browser admission composed with the PIN profile runtime."""

from contextlib import asynccontextmanager
import os
import stat
import sys

from pydantic import ValidationError

from laomedo.integrations.langflow.authentication.adapter import PrivateSessionAdapter
from laomedo.integrations.langflow.authentication.boundary import (
    PrivateResponseBoundary,
)
from laomedo.integrations.langflow.authentication.errors import PrivateSessionError
from laomedo.integrations.langflow.authentication.models import PrivateRuntimeMarker
from laomedo.integrations.langflow.authentication.policy import (
    PrivateAccessPolicy,
    PrivateGitHubResponsePolicy,
)
from laomedo.integrations.langflow.authentication.settings import PrivateBrowserSettings
from laomedo.integrations.langflow.authentication.store import PrivateSessionStore


class PrivateBrowserRuntime:
    """Own one native broker process and a private directory outside public roots."""

    def __init__(self, settings: PrivateBrowserSettings):
        self.settings = settings
        self.root = settings.runtime_root
        self._owner_file = None
        self._upstream_lifespan = None

    def _admit_directory(self):
        if sys.platform != "win32":
            raise PrivateSessionError()
        try:
            for path in (self.root, *self.root.parents):
                if (path / ".git").exists():
                    raise PrivateSessionError()
                if path.exists():
                    attributes = getattr(path.lstat(), "st_file_attributes", 0)
                    if (
                        path.is_symlink()
                        or attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
                    ):
                        raise PrivateSessionError()
            for root in (*self.settings.public_roots, *self.settings.agent_mounts):
                forbidden = root.resolve()
                private = self.root.resolve()
                if private.is_relative_to(forbidden) or forbidden.is_relative_to(
                    private
                ):
                    raise PrivateSessionError()
            marker_path = self.root / "private-github.json"
            marker = PrivateRuntimeMarker(origin=self.settings.origin)
            if self.root.exists() and any(self.root.iterdir()):
                if (
                    marker_path.is_symlink()
                    or PrivateRuntimeMarker.model_validate_json(
                        marker_path.read_text(encoding="utf-8-sig")
                    )
                    != marker
                ):
                    raise PrivateSessionError()
            else:
                self.root.mkdir(parents=True, exist_ok=True)
                marker_path.write_text(marker.model_dump_json(), encoding="utf-8")
        except (OSError, ValidationError):
            raise PrivateSessionError() from None

    def configure(self, app):
        """Install after explicit profile setup; default public previews stay unchanged."""
        if (
            self._upstream_lifespan is not None
            or not getattr(app.state, "local_profiles_enabled", False)
            or app.debug
        ):
            raise PrivateSessionError()
        self._admit_directory()
        store = PrivateSessionStore(self.root / "private-sessions.sqlite")
        self.policy = PrivateAccessPolicy(store, self.settings)
        app.state.private_access_policy = self.policy
        from laomedo.integrations.langflow.authentication.routes import router
        from laomedo.integrations.langflow.authentication.connections import (
            connection_router,
        )
        from laomedo.github.connections.journal import GitHubConnectionJournal
        from laomedo.github.connections.service import GitHubConnectionService
        from laomedo.github.connections.settings import GITHUB_CALLBACK_PATH
        from laomedo.host.credentials.github.vault import WindowsCredentialVault

        connections = GitHubConnectionService(
            GitHubConnectionJournal(self.root / "connections.sqlite"),
            WindowsCredentialVault(),
            callback_uri=self.settings.origin + GITHUB_CALLBACK_PATH,
            commit_lock=self.policy.lock,
        )
        app.state.private_github_connections = connections
        app.include_router(router)
        app.include_router(connection_router)
        app.add_middleware(PrivateSessionAdapter, store=store, policy=self.policy)
        app.add_middleware(
            PrivateResponseBoundary,
            policy=self.policy,
            resource_policy=PrivateGitHubResponsePolicy(connections),
        )
        self._upstream_lifespan = app.router.lifespan_context
        app.router.lifespan_context = self.lifespan

    def _claim_process(self):
        """Hold an exclusive native byte-range lock for the broker's full lifetime."""
        import msvcrt

        try:
            path = self.root / "broker.lock"
            if path.is_symlink() or (
                path.exists()
                and getattr(path.lstat(), "st_file_attributes", 0)
                & stat.FILE_ATTRIBUTE_REPARSE_POINT
            ):
                raise PrivateSessionError()
            owner_file = path.open("a+b")
            try:
                if path.stat().st_size == 0:
                    owner_file.write(b"0")
                    owner_file.flush()
                    os.fsync(owner_file.fileno())
                owner_file.seek(0)
                msvcrt.locking(owner_file.fileno(), msvcrt.LK_NBLCK, 1)
            except Exception:
                owner_file.close()
                raise
            self._owner_file = owner_file
        except OSError:
            raise PrivateSessionError() from None

    def _release_process(self):
        import msvcrt

        if self._owner_file is not None:
            owner_file, self._owner_file = self._owner_file, None
            try:
                owner_file.seek(0)
                msvcrt.locking(owner_file.fileno(), msvcrt.LK_UNLCK, 1)
            finally:
                owner_file.close()

    @asynccontextmanager
    async def lifespan(self, app):
        self._claim_process()
        try:
            async with self._upstream_lifespan(app) as state:
                self.policy.verify_runtime()
                yield state
        finally:
            self._release_process()
