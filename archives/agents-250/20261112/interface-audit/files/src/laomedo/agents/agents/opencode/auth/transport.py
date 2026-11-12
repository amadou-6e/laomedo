"""Implementation owned by host / credentials / opencode / transport."""

from __future__ import annotations

from urllib.request import HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ValueError("opencode_auth_redirect_rejected")
