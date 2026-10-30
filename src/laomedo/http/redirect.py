"""Refuse forwarding redirects without introducing feature-specific errors."""

from urllib.request import HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    """Keep urllib's existing refusal/HTTPError behavior for return-None consumers."""

    def redirect_request(self, *_args, **_kwargs):
        """Do not construct a request to the redirect destination."""
        return None
