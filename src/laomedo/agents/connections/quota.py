"""Lease-gated memory observations over exact saved-account zero-turn reads."""

from collections import OrderedDict
from concurrent.futures import Future, TimeoutError
import time

from laomedo.host.credentials.siwc.errors import AuthError
from laomedo.agents.errors import RunnerError
from laomedo.agents.connections.errors import ProviderConnectionError
from laomedo.agents.connections.models import SubscriptionBinding
from laomedo.agents.connections.models import SubscriptionCacheEntry
from laomedo.agents.connections.models import SubscriptionObservation
from laomedo.agents.connections.settings import SUBSCRIPTION_CACHE_ENTRIES
from laomedo.agents.connections.settings import SUBSCRIPTION_FRESH_SECONDS
from laomedo.agents.connections.settings import SUBSCRIPTION_RETAIN_SECONDS
from laomedo.agents.connections.settings import SUBSCRIPTION_RETRY_SECONDS
from laomedo.agents.connections.settings import SUBSCRIPTION_WAIT_SECONDS


class SubscriptionObservations:
    """Coalesce per-account native reads while separately fencing each browser lease."""

    def __init__(self, service, *, clock=time.time):
        """Bind the existing lifecycle lock; construction performs no provider operation."""
        self.service = service
        self.clock = clock
        self.entries = OrderedDict()
        self.visible = OrderedDict()
        self.flights = {}

    def invalidate(self, *, profile_id=None, connection_id=None, lease_hash=None):
        """Erase matching cached visibility; never interrupt another valid native waiter."""
        with self.service._lock:
            for key in list(self.visible):
                binding, lease = key
                if (
                    (profile_id is None or binding.profile_id == profile_id)
                    and (
                        connection_id is None or binding.connection_id == connection_id
                    )
                    and (lease_hash is None or lease == lease_hash)
                ):
                    self.visible.pop(key, None)
            if lease_hash is None:
                for binding in list(self.entries):
                    if (profile_id is None or binding.profile_id == profile_id) and (
                        connection_id is None or binding.connection_id == connection_id
                    ):
                        self.entries.pop(binding, None)

    def read(self, profile_id, connection_id, generation, lease_hash):
        """Read memory only; never start native work, refresh credentials or consult ambient login."""
        binding = SubscriptionBinding(
            profile_id=profile_id, connection_id=connection_id, generation=generation
        )
        with self.service._lock:
            record = self._check(binding, lease_hash)
            self._prune()
            return self._result(
                binding,
                lease_hash,
                unsupported=record.provider != "codex"
                or record.client_id != "codex-native",
            )

    def refresh(self, profile_id, connection_id, generation, lease_hash):
        """Explicitly observe one native binding; each waiter must still own its lease on return."""
        binding = SubscriptionBinding(
            profile_id=profile_id, connection_id=connection_id, generation=generation
        )
        leader = False
        with self.service._lock:
            record = self._check(binding, lease_hash)
            self._prune()
            if record.provider != "codex" or record.client_id != "codex-native":
                return self._result(binding, lease_hash, unsupported=True)
            entry = self.entries.get(binding)
            now = self.clock()
            if entry is not None and (
                (
                    entry.reason is None
                    and entry.stale_after is not None
                    and now < entry.stale_after
                )
                or now - entry.attempted_at < SUBSCRIPTION_RETRY_SECONDS
            ):
                self.visible[(binding, lease_hash)] = None
                self._prune()
                return self._result(binding, lease_hash)
            flight = self.flights.get(binding)
            if flight is None:
                if len(self.flights) >= SUBSCRIPTION_CACHE_ENTRIES:
                    raise ProviderConnectionError("provider_connection_busy")
                flight = Future()
                self.flights[binding] = flight
                leader = True
        if leader:
            self._observe(binding, flight)
        else:
            try:
                flight.result(timeout=SUBSCRIPTION_WAIT_SECONDS)
            except TimeoutError:
                raise ProviderConnectionError("provider_runner_unavailable") from None
        with self.service._lock:
            self._check(binding, lease_hash)
            self._prune()
            self.visible[(binding, lease_hash)] = None
            self._prune()
            return self._result(binding, lease_hash)

    def _check(self, binding, lease_hash=None):
        """Require exact ownership, live local credential metadata and a nonrevoked lease."""
        if self.service._closing or (
            self.service.controllers is not None and self.service.controllers.closed
        ):
            raise ProviderConnectionError("provider_runner_unavailable")
        if lease_hash is not None:
            if not lease_hash:
                raise ProviderConnectionError("provider_session_required")
            self.service.check_lease(lease_hash)
        record = self.service.admitted(
            binding.profile_id, binding.connection_id, binding.generation
        )
        if record.provider == "codex" and record.client_id == "codex-native":
            try:
                self.service.codex.saved_identity(binding.profile_id, record)
            except Exception:
                self.invalidate(
                    profile_id=binding.profile_id, connection_id=binding.connection_id
                )
                raise ProviderConnectionError(
                    "provider_connection_unavailable"
                ) from None
        return record

    def _prune(self):
        """Bound retained observations and lease visibility without evicting native flights."""
        now = self.clock()
        for binding, entry in list(self.entries.items()):
            if now - entry.attempted_at >= SUBSCRIPTION_RETAIN_SECONDS or (
                entry.observed_at is not None
                and now - entry.observed_at >= SUBSCRIPTION_RETAIN_SECONDS
            ):
                self.entries.pop(binding, None)
        while len(self.entries) > SUBSCRIPTION_CACHE_ENTRIES:
            self.entries.popitem(last=False)
        for key in list(self.visible):
            if key[0] not in self.entries:
                self.visible.pop(key, None)
        while len(self.visible) > SUBSCRIPTION_CACHE_ENTRIES:
            self.visible.popitem(last=False)

    def _result(self, binding, lease_hash, *, unsupported=False):
        """Project only this lease's latest authorized snapshot and safe recovery state."""
        entry = (
            self.entries.get(binding) if (binding, lease_hash) in self.visible else None
        )
        state = "not_checked"
        if unsupported:
            state = "unavailable"
        elif entry is not None:
            state = (
                "unavailable"
                if entry.snapshot is None
                else (
                    "stale"
                    if entry.reason or self.clock() >= entry.stale_after
                    else "ready"
                )
            )
        return SubscriptionObservation(
            connection_id=binding.connection_id,
            generation=binding.generation,
            state=state,
            reason="unsupported" if unsupported else entry.reason if entry else None,
            observed_at=entry.observed_at if entry else None,
            stale_after=entry.stale_after if entry else None,
            snapshot=entry.snapshot if entry else None,
        )

    def _observe(self, binding, flight):
        """Retain a safe read only after exact native teardown and generation revalidation."""
        snapshot = None
        reason = None
        try:
            if self.service.controllers is None:
                raise ProviderConnectionError("provider_runner_unavailable")
            snapshot = self.service.controllers.subscription_limits(binding)
        except (ProviderConnectionError, RunnerError) as error:
            reason = (
                "busy" if error.code == "provider_connection_busy" else "refresh_failed"
            )
        except Exception:
            # Never retain a raw exception or provider body in cache/future/logs.
            reason = "refresh_failed"
        with self.service._lock:
            try:
                self._check(binding)
                now = self.clock()
                previous = self.entries.get(binding)
                if reason is None:
                    resets = [
                        window.resets_at
                        for bucket in snapshot.buckets
                        for window in bucket.windows
                        if window.resets_at is not None
                    ]
                    stale_after = min([now + SUBSCRIPTION_FRESH_SECONDS, *resets])
                    entry = SubscriptionCacheEntry(
                        snapshot=snapshot,
                        observed_at=now,
                        stale_after=stale_after,
                        attempted_at=now,
                    )
                else:
                    entry = SubscriptionCacheEntry(
                        snapshot=previous.snapshot if previous else None,
                        observed_at=previous.observed_at if previous else None,
                        stale_after=previous.stale_after if previous else None,
                        attempted_at=now,
                        reason=reason,
                    )
                self.entries[binding] = entry
                self.entries.move_to_end(binding)
                self._prune()
            except (ProviderConnectionError, AuthError, OSError, ValueError, KeyError):
                self.invalidate(
                    profile_id=binding.profile_id, connection_id=binding.connection_id
                )
            finally:
                self.flights.pop(binding, None)
                flight.set_result(None)
