"""Revalidate private browser admission before a private response is released."""

from starlette.responses import JSONResponse

from laomedo.integrations.langflow.authentication.errors import (
    PrivateSessionError,
    PrivateSessionRequired,
    PrivateRequestRefused,
)
from laomedo.integrations.langflow.authentication.models import PrivateBrowserContext
from laomedo.github.connections.errors import (
    GitHubConnectionError,
    GitHubConnectionChanged,
    GitHubRepositoryAccessError,
)


class PrivateResponseBoundary:
    """Keep logout ordered against private responses without touching public routes."""

    def __init__(self, app, *, policy, resource_policy=None):
        self.app = app
        self.policy = policy
        self.resource_policy = resource_policy

    def _private_path(self, path):
        return path == "/api/v1/laomedo/private-session" or any(
            path == prefix or path.startswith(prefix + "/")
            for prefix in (
                "/api/v1/laomedo/github-connections",
                "/api/v1/laomedo/private-skills",
            )
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self._private_path(scope.get("path", "")):
            return await self.app(scope, receive, send)
        locked = False
        refused = False

        async def observe(message):
            nonlocal locked, refused
            if refused:
                return
            if message["type"] == "http.response.start" and (
                200 <= message["status"] < 300 or message["status"] == 304
            ):
                context = scope.get("state", {}).get("private_browser_context")
                try:
                    if not isinstance(context, PrivateBrowserContext):
                        raise PrivateSessionRequired()
                    await self.policy.lock.acquire()
                    locked = True
                    await self.policy.revalidate(context)
                    if scope.get("path") != "/api/v1/laomedo/private-session":
                        if self.resource_policy is None:
                            raise GitHubConnectionError()
                        self.resource_policy.revalidate(
                            scope.get("state", {}).get("github_response_binding"),
                            context,
                        )
                except PrivateSessionError as error:
                    refused = True
                    return await self._refuse(scope, receive, send, error)
                except GitHubConnectionError as error:
                    refused = True
                    return await self._refuse(scope, receive, send, error)
                except Exception:
                    refused = True
                    return await self._refuse(
                        scope, receive, send, PrivateSessionError()
                    )
            if message["type"] == "http.response.start":
                message = {
                    **message,
                    "headers": [
                        (name, value)
                        for name, value in message.get("headers", [])
                        if name.lower()
                        not in {b"cache-control", b"x-content-type-options"}
                    ]
                    + [
                        (b"cache-control", b"no-store"),
                        (b"x-content-type-options", b"nosniff"),
                    ],
                }
            await send(message)

        try:
            await self.app(scope, receive, observe)
        finally:
            if locked:
                self.policy.lock.release()

    async def _refuse(self, scope, receive, send, error):
        await JSONResponse(
            {"code": error.code},
            status_code=(
                409
                if isinstance(
                    error,
                    (
                        PrivateSessionRequired,
                        PrivateRequestRefused,
                        GitHubConnectionChanged,
                        GitHubRepositoryAccessError,
                    ),
                )
                else 503
            ),
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )(scope, receive, send)
