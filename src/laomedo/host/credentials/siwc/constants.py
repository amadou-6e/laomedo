"""Constants shared by the owning feature; mutable state has one owner."""

from __future__ import annotations

AUTH_ORIGIN = "https://auth.openai.com"


RESOURCE = "https://api.openai.com/v1"


SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"


NEEDED = frozenset(
    {"openid", "offline_access", "resource.invoke", "chatgpt.tokens.use.direct"}
)


MIN_DISPATCH_TTL = 300
