"""Implementation owned by host / leases / grants."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
from laomedo.host.leases.models import GrantWindow, LeaseClock, LeaseGrant
import secrets
import threading
import time


class GrantBook:
    """Thread-safe registry of run-scoped grants with independent expiry clocks."""

    def __init__(self, events: Path):
        self.lock = threading.Lock()
        self.by_digest: dict[str, LeaseGrant] = {}
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
        window = GrantWindow(
            clock=LeaseClock(wall=now, monotonic=time.monotonic()),
            wall_deadline=expires_not_after,
            monotonic_deadline=expires_not_after_monotonic,
        )
        with self.lock:
            self.by_digest[sha256(secret.encode()).hexdigest()] = (
                LeaseGrant.from_window(grant_id, token, window)
            )
        return grant_id, secret

    def renew(
        self,
        token: str,
        now: float,
        expires_not_after: float,
        expires_not_after_monotonic: float,
    ) -> None:
        window = GrantWindow(
            clock=LeaseClock(wall=now, monotonic=time.monotonic()),
            wall_deadline=expires_not_after,
            monotonic_deadline=expires_not_after_monotonic,
        )
        with self.lock:
            for grant in self.by_digest.values():
                if (
                    grant.bound_to(token)
                    and grant.revoked_at is None
                    and grant.expires_monotonic > window.clock.monotonic
                ):
                    grant.renew(window)

    def revoke(self, token: str, now: float) -> list[str]:
        revoked = []
        with self.lock:
            for grant in self.by_digest.values():
                if grant.bound_to(token) and grant.revoked_at is None:
                    grant.revoke(now)
                    revoked.append(grant.grant_id)
        return revoked

    def check(self, secret: str) -> tuple[bool, str | None]:
        clock = LeaseClock(wall=time.time(), monotonic=time.monotonic())
        with self.lock:
            grant = self.by_digest.get(sha256(secret.encode()).hexdigest())
            accepted = grant is not None and grant.accepts(clock)
            grant_id = grant.grant_id if grant else None
            with self.events.open("a", encoding="utf-8") as log:
                log.write(
                    json.dumps(
                        {"at": clock.wall, "grant_id": grant_id, "accepted": accepted}
                    )
                    + "\n"
                )
        return accepted, grant_id
