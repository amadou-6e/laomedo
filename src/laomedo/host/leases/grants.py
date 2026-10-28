"""Implementation owned by host / leases / grants."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import laomedo.host.leases.settings as _leases_settings
import secrets
import threading
import time


class GrantBook:
    """Thread-safe registry of run-scoped synthetic write grants."""

    def __init__(self, events: Path):
        self.lock = threading.Lock()
        self.by_digest: dict[str, dict] = {}
        self.events = events

    def issue(
        self,
        token: str,
        now: float,
        expires_not_after: float,
        expires_not_after_monotonic: float,
    ) -> tuple[str, str]:
        secret = secrets.token_hex(32)
        grant_id = "grant-" + secrets.token_hex(8)
        issued_monotonic = time.monotonic()
        with self.lock:
            self.by_digest[sha256(secret.encode()).hexdigest()] = {
                "grant_id": grant_id,
                "lease_token": token,
                "expires_at": min(
                    now + _leases_settings.GRANT_TTL_SECONDS, expires_not_after
                ),
                "issued_monotonic": issued_monotonic,
                "expires_monotonic": min(
                    issued_monotonic + _leases_settings.GRANT_TTL_SECONDS,
                    expires_not_after_monotonic,
                ),
                "revoked_at": None,
            }
        return grant_id, secret

    def renew(
        self,
        token: str,
        now: float,
        expires_not_after: float,
        expires_not_after_monotonic: float,
    ) -> None:
        now_monotonic = time.monotonic()
        with self.lock:
            for grant in self.by_digest.values():
                if (
                    grant["lease_token"] == token
                    and grant["revoked_at"] is None
                    and grant["expires_monotonic"] > now_monotonic
                ):
                    grant["expires_at"] = min(
                        now + _leases_settings.GRANT_TTL_SECONDS, expires_not_after
                    )
                    grant["expires_monotonic"] = min(
                        now_monotonic + _leases_settings.GRANT_TTL_SECONDS,
                        expires_not_after_monotonic,
                    )

    def revoke(self, token: str, now: float) -> list[str]:
        revoked = []
        with self.lock:
            for grant in self.by_digest.values():
                if grant["lease_token"] == token and grant["revoked_at"] is None:
                    grant["revoked_at"] = now
                    revoked.append(grant["grant_id"])
        return revoked

    def check(self, secret: str) -> tuple[bool, str | None]:
        now = time.time()
        now_monotonic = time.monotonic()
        with self.lock:
            grant = self.by_digest.get(sha256(secret.encode()).hexdigest())
            accepted = (
                grant is not None
                and grant["revoked_at"] is None
                and now < grant["expires_at"]
                and grant["issued_monotonic"]
                <= now_monotonic
                < grant["expires_monotonic"]
            )
            grant_id = grant["grant_id"] if grant else None
            with self.events.open("a", encoding="utf-8") as log:
                log.write(
                    json.dumps({"at": now, "grant_id": grant_id, "accepted": accepted})
                    + "\n"
                )
        return accepted, grant_id
