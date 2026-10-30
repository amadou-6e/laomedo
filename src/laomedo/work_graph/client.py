"""Implementation owned by work_graph / client."""

from __future__ import annotations

from threading import Lock
from urllib import error
from urllib import parse
from urllib import request
import json
from laomedo.work_graph.runs.errors import LaunchError


class LangflowLocalClient:
    def __init__(self, base_url):
        parsed = parse.urlsplit(base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise LaunchError("langflow_loopback_required")
        self.base_url = base_url.rstrip("/")
        self._token_lock = Lock()
        self._token = self._login()

    def _login(self):
        try:
            with request.urlopen(
                self.base_url + "/api/v1/auto_login", timeout=15
            ) as response:
                token = json.load(response)["access_token"]
        except (OSError, ValueError, KeyError):
            raise LaunchError("langflow_local_login_unavailable") from None
        if not isinstance(token, str) or not token:
            raise LaunchError("langflow_local_login_unavailable")
        return token

    def fetch(self, flow_id):
        if not isinstance(flow_id, str) or not flow_id or "/" in flow_id:
            raise LaunchError("saved_flow_identity_unavailable")
        for attempt in range(2):
            token = self._token
            req = request.Request(
                self.base_url + "/api/v1/flows/" + parse.quote(flow_id),
                headers={
                    "Authorization": "Bearer " + token,
                    "Accept": "application/json",
                },
            )
            try:
                with request.urlopen(req, timeout=30) as response:
                    return json.load(response)
            except error.HTTPError as exc:
                exc.close()
                if exc.code == 401 and attempt == 0:
                    # Refresh only the local app login, then repeat this read.
                    # Never repeat a launch or model request on authentication failure.
                    with self._token_lock:
                        if self._token == token:
                            self._token = self._login()
                    continue
                raise LaunchError("saved_flow_fetch_failed") from None
            except (OSError, ValueError):
                raise LaunchError("saved_flow_fetch_failed") from None
