"""Refuse forwarding redirects without introducing feature-specific errors."""

from urllib.request import HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    """Refuse redirect forwarding through urllib's HTTPError path."""

    def redirect_request(self, *_args, **_kwargs):
        """Do not construct a request to the redirect destination."""
        return None
