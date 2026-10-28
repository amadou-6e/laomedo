"""Opt-in local HTTP boundary for a host-owned Langflow join controller.

The caller supplies the bridge token, saved-flow resolver and runner transport.
This module does not start a service or alter an existing Langflow installation."""

from __future__ import annotations

from urllib import error
from urllib import request
from urllib.parse import urlsplit
import json


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *_):
        return None


class RunnerHTTPTransport:
    """Authenticated host-side client for the existing local Codex runner."""

    def __init__(self, base_url, token, *, timeout=30, provider="codex"):
        if provider not in {"codex", "claude"}:
            raise ValueError("unsupported_join_provider")
        self.provider = provider
        parsed = urlsplit(str(base_url).rstrip("/"))
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("local_runner_url_required")
        if not isinstance(token, str) or not token or not 1 <= timeout <= 120:
            raise ValueError("runner_transport_config_invalid")
        self.base_url = str(base_url).rstrip("/")
        self.token = token
        self.timeout = timeout
        self.opener = request.build_opener(_NoRedirect())

    def _call(self, method, path, payload=None):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.base_url + path,
            data=body,
            method=method,
            headers={
                "Authorization": "Bearer " + self.token,
                "Content-Type": "application/json",
            },
        )
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                if int(response.headers.get("Content-Length", "0") or 0) > 1048576:
                    raise RuntimeError("runner_response_too_large")
                raw = response.read(1048577)
        except error.HTTPError as exc:
            if method == "GET" and exc.code == 404 and path.startswith("/v1/requests/"):
                raise LookupError("request_not_found") from None
            raise RuntimeError("runner_http_rejected") from None
        except (error.URLError, TimeoutError, OSError):
            raise RuntimeError("runner_transport_unknown") from None
        if len(raw) > 1048576:
            raise RuntimeError("runner_response_too_large")
        try:
            value = json.loads(raw)
        except (ValueError, TypeError):
            raise RuntimeError("runner_invalid_response") from None
        if not isinstance(value, dict):
            raise RuntimeError("runner_invalid_response")
        return value

    def start_async(self, body):
        return self._call("POST", "/v1/runs/async", body)

    def lookup_request(self, request_id):
        return self._call("GET", "/v1/requests/" + str(request_id))

    def status(self, run_id):
        return self._call("GET", "/v1/runs/" + str(run_id))

    def cancel(self, run_id):
        return self._call("POST", "/v1/runs/" + str(run_id) + "/cancel", {})
