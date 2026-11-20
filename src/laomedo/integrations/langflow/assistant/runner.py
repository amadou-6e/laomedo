"""Saved-account assistant client around the guarded runner HTTP API."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener
from laomedo.host.http import NoRedirect
from laomedo.integrations.langflow.assistant.errors import AssistantError


class AssistantRunner:
    """Use one profile's exact saved account; shared controllers own native lifecycle."""

    def __init__(
        self,
        settings,
        owner,
        provider="codex",
        connection_id=None,
        connection_generation=None,
        *,
        controllers=None,
    ):
        """Retain an exact saved-account binding; own no listener or credentials."""
        self.settings, self.owner, self.provider = settings, owner, provider
        self.controllers = controllers
        self.connection_id = connection_id
        self.connection_generation = connection_generation
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def manager(self):
        """Resolve the installed saved-account lifecycle owner without fallback."""

        if (
            self.controllers is None
            or self.connection_id is None
            or self.connection_generation is None
        ):
            raise AssistantError("assistant_setup_required", 409)
        return self.controllers

    @property
    def instance_id(self):
        """Observe the shared manager's exact assistant runtime identity."""
        return self.manager().assistant_instance_id(
            self.owner, self.connection_id, self.connection_generation
        )

    def request(self, method, path, body=None):
        """Issue one bounded authenticated local request without proxy, redirect or replay."""
        if not path.startswith("/v1/") or ".." in path or "\r" in path or "\n" in path:
            raise AssistantError("assistant_request_invalid", 400)
        from laomedo.agents.connections.errors import ProviderConnectionError
        from uuid import UUID

        parts = path.split("?", 1)[0].strip("/").split("/")
        run_id = None
        if len(parts) >= 3 and parts[:2] == ["v1", "runs"] and parts[2] != "async":
            try:
                run_id = str(UUID(parts[2]))
            except ValueError:
                raise AssistantError("assistant_request_invalid", 400) from None
        try:
            url, token_path = self.manager().assistant_endpoint(
                self.owner,
                self.connection_id,
                self.connection_generation,
                run_id=run_id,
            )
            token = token_path.read_text(encoding="utf-8").strip()
        except ProviderConnectionError as error:
            raise AssistantError(error.code, 409) from None
        request = Request(
            url + path,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
            },
        )
        try:
            with self.opener.open(request, timeout=30) as response:
                data = response.read(4194305)
            if len(data) > 4194304:
                raise AssistantError("assistant_runner_response_too_large", 503)
            return json.loads(data)
        except HTTPError as error:
            try:
                payload = json.loads(error.read(65536))
                code = payload.get("error_category") or payload.get("code")
                if (
                    not isinstance(code, str)
                    or not code.replace("_", "").isalnum()
                    or len(code) > 100
                ):
                    code = "assistant_runner_unavailable"
            except (ValueError, TypeError):
                code = "assistant_runner_unavailable"
            finally:
                error.close()
            raise AssistantError(code, 409 if error.code < 500 else 503) from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise AssistantError("assistant_dispatch_unknown", 503) from None

    def shutdown(self):
        """Leave shared saved-account cleanup and listener ownership with its manager."""

    def has_live_session(self, run_id):
        """Read the native owner's actual in-memory retention, never a record claim."""
        try:
            return self.manager().assistant_live_session(
                self.owner, self.connection_id, self.connection_generation, run_id
            )
        except ProviderConnectionError as error:
            raise AssistantError(error.code, 409) from None

    def is_settled(self, run_id):
        """Read actual owned cleanup facts through the controller boundary."""
        return self.manager().assistant_settled(
            self.owner, self.connection_id, self.connection_generation, run_id
        )
