"""Implementation owned by skills / sources / transport."""

from __future__ import annotations
import urllib.request

import urllib.error


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None
