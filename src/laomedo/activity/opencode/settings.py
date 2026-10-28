"""Feature settings and fixed protocol values; mutable state has one owner."""

from __future__ import annotations

ALLOWED = {
    "message.updated",
    "message.part.updated",
    "message.part.delta",
    "message.removed",
    "message.part.removed",
    "session.created",
    "session.updated",
    "session.status",
    "session.idle",
    "session.error",
}


SECRET_KEYS = {
    "authorization",
    "password",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
}
