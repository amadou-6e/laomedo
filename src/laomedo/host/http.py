"""Refuse forwarding redirects without introducing feature-specific errors."""

from urllib.request import HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    """Refuse redirect forwarding through urllib's HTTPError path."""

    def redirect_request(self, *_args, **_kwargs):
        """Reject urllib's redirect callback without constructing a destination request.

        All positional and keyword callback arguments are ignored. Returning
        None makes the standard-library opener raise HTTPError for the redirect
        response instead of forwarding the request. No network call is made here.
        """
        return None
