"""Bind graph reads to the authenticated browser's current private lease."""

from contextvars import ContextVar
from uuid import UUID

from pydantic import SecretStr
from starlette.requests import Request

from laomedo.github.connections.errors import GitHubRepositoryAccessError
from laomedo.integrations.langflow.authentication.models import PrivateBrowserContext
from laomedo.integrations.langflow.authentication.policy import PrivateGitHubAdmission
from laomedo.integrations.langflow.authentication.settings import (
    PRIVATE_SESSION_COOKIE_NAME,
)


class PrivateGraphBindings:
    """Keep browser authority request-local and separate from graph-supplied fields."""

    admission = ContextVar("laomedo_private_graph_admission", default=None)

    @classmethod
    async def read_pr(cls, component, account, repository, number):
        admission = cls.admission.get()
        if admission is None:
            raise GitHubRepositoryAccessError()
        policy, context, access = admission
        try:
            owner = UUID(str(component.user_id))
            connection = UUID(str(account))
        except (ValueError, TypeError, AttributeError):
            raise GitHubRepositoryAccessError() from None
        if owner != context.session.owner_id:
            raise GitHubRepositoryAccessError()
        scope = PrivateGitHubAdmission(policy, context).scope()
        await scope.revalidate()
        record = access.connections.journal.get(owner, connection)
        matches = [
            entry
            for entry in (record.repositories if record else [])
            if entry.full_name.casefold() == repository.casefold()
        ]
        if len(matches) != 1:
            raise GitHubRepositoryAccessError()
        return (await access.read(scope, connection, matches[0].id, number)).payload


class PrivateGraphBoundary:
    """Derive the graph's private lease from cookies authenticated by local profiles."""

    def __init__(self, app, *, policy, access):
        self.app, self.policy, self.access = app, policy, access

    async def __call__(self, scope, receive, send):
        admission = None
        if scope["type"] == "http" and scope.get("path", "").startswith("/api/"):
            request = Request(scope)
            if (
                self.policy.same_origin(request)
                and not request.headers.get("authorization")
                and not request.headers.get("x-api-key")
                and "x-api-key" not in request.query_params
            ):
                try:
                    from langflow.services.auth.utils import oauth2_login

                    token = await oauth2_login(request)
                    owner = await self.policy.owner_from_token(token)
                    cookie = request.cookies.get(PRIVATE_SESSION_COOKIE_NAME)
                    session = (
                        self.policy.store.resolve(SecretStr(cookie), owner)
                        if cookie and owner
                        else None
                    )
                    if session is not None:
                        context = PrivateBrowserContext(
                            session=session,
                            cookie=SecretStr(cookie),
                            upstream_token=SecretStr(token),
                        )
                        admission = (self.policy, context, self.access)
                except Exception:
                    admission = None
        marker = PrivateGraphBindings.admission.set(admission)
        try:
            await self.app(scope, receive, send)
        finally:
            PrivateGraphBindings.admission.reset(marker)
