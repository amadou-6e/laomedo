"""Invocation target interfaces for provider migration (#277)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Protocol

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from laomedo.agents.agents.base.models.invocation import (
        InvocationContext,
        InvocationResult,
        InvocationRequest,
        SettlementResult,
        SettlementView,
    )
    from laomedo.agents.agents.base.models.failures import FailureObservation
    from laomedo.agents.agents.base.models.journal import (
        CorrectionEntry,
        DispatchEntry,
        EvidenceEntry,
        LeaseEntry,
        NativeSessionEntry,
        OwnershipEntry,
        RuntimeIdentityEntry,
        ScopeCleanupEntry,
        TurnEntry,
    )
    from laomedo.host.leases.client import LeaseClient
    from pydantic import JsonValue


class StopSource(Protocol):
    """Reason-bound Event-style input for existing lease/native setters."""

    def set(self) -> None:
        """Request this source's private stop reason, never acknowledgement."""


class StopContext(Protocol):
    """Concrete StopSignal's interface; public cancellation projection is unchanged."""

    @property
    def reason(self) -> str | None:
        """First private reason; infrastructure failure is distinguishable internally."""

    def is_set(self) -> bool:
        """Observe a request, never infer native interruption or cleanup."""

    def wait(self, timeout: float | None = None) -> bool:
        """Event-compatible bounded observation for native monitors."""

    def request(self, reason: str) -> None:
        """Retain the first reason and notify subscribers outside the state lock."""

    def source(self, reason: str) -> StopSource:
        """Bind an explicit reason for a legacy Event-style set caller."""

    def subscribe(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Subscribe race-safely, including an already-set signal; return unsubscribe."""


class BaseAgentRunner(ABC):
    """Interchangeable admitted execution, independent of native resource topology."""

    @abstractmethod
    def open_activity_attempt(self, context: InvocationContext) -> dict[str, JsonValue]:
        """Construct the provider's current baseline/record shape for journal writes."""

    @abstractmethod
    def run(
        self,
        request: InvocationRequest,
        journal: BaseInvocationJournal,
        stop: StopContext,
    ) -> InvocationResult:
        """Execute Fresh/Resume, native turns and cleanup on the creator thread.

        Return a result for every failure after reservation/lease acquisition;
        retain settlement for every status with a surviving lease. Never freeze,
        mutate Agent records, substitute a model or fall back to Fresh on Resume.
        """


class BaseInvocationJournal(ABC):
    """Agent-owned durable writes; success precedes the guarded native side effect.

    Entries carry detached provider fields, never the Agent's mutable dictionary.
    Implementations serialize writes under the existing control lock and preserve
    persisted extensions, field presence and errors. No journal method dispatches.
    """

    @abstractmethod
    def reserve_ownership(self, entry: OwnershipEntry) -> None:
        """Persist exact scope ownership before allocation."""

    @abstractmethod
    def bind_native_session(self, entry: NativeSessionEntry) -> None:
        """Persist actual native identity before its first prompt."""

    @abstractmethod
    def reserve_dispatch(self, entry: DispatchEntry) -> None:
        """Reserve the native turn before sending it."""

    @abstractmethod
    def mark_dispatched(self, entry: DispatchEntry) -> None:
        """Record the observed dispatch fact without claiming completion."""

    @abstractmethod
    def record_turn(self, entry: TurnEntry) -> None:
        """Persist native terminal facts with their original identity."""

    @abstractmethod
    def record_lease(self, entry: LeaseEntry) -> None:
        """Persist supervision/grant binding; leases are not plan resources."""

    @abstractmethod
    def register_publication(self, lease: LeaseClient) -> None:
        """Register through the Agent-owned publication authority and record."""

    @abstractmethod
    def bind_runtime_identity(self, entry: RuntimeIdentityEntry) -> None:
        """Persist admitted credential/runtime fingerprints without secrets."""

    @abstractmethod
    def record_correction_pending(self, entry: CorrectionEntry) -> None:
        """Preserve pending correction ordering before its next native turn."""

    @abstractmethod
    def record_scope_cleanup(self, entry: ScopeCleanupEntry) -> None:
        """Persist scoped cleanup truth separately from terminal success."""

    @abstractmethod
    def record_evidence(self, entry: EvidenceEntry) -> None:
        """Persist live evidence/attempt updates without interpreting read-time Activity."""


class BasePostFreezeSettlement(ABC):
    """Lease/evidence settlement surviving an attempt, including failure/cancel."""

    @abstractmethod
    def settle(self, view: SettlementView) -> SettlementResult:
        """Settle a completed frozen attempt through a detached record view.

        Return typed updates/cleanup; unverified settlement demotes completion
        and clears snapshot/output fields through the Agent's existing policy.
        Agent converts escaping exceptions to verified=False; calls are serialized
        after freeze, never while the runner still owns the lease.
        """

    @abstractmethod
    def abort(
        self, view: SettlementView, failure: FailureObservation | None
    ) -> SettlementResult:
        """Resolve failed/cancelled/freeze-failed supervision, serialized by Agent.

        Agent converts escaping exceptions to verified=False. No frozen snapshot
        is required; leases retain their provider-specific finish/heartbeat policy.
        """
