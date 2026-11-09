"""Target provider contracts for #277; provider inheritance is not migrated yet.

BaseAgent stays in agent.py. Values are defined in models.py; type-only imports
keep contracts independent of model construction and optional Docker imports.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
import threading
from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pydantic import JsonValue
    from py_docker.execution.models import CommandResult as DockerCommandResult
    from py_docker.jobs.models import ContainerJob
    from py_docker.sessions.models import ContainerSession
    from py_docker.streams.models import Line
    from laomedo.agents.activity.models import ActivityProjection
    from laomedo.agents.agents.base.models import (
        AttemptContext,
        AttemptRequest,
        AttemptOutcome,
        OwnershipEntry,
        NativeSessionEntry,
        DispatchEntry,
        TurnEntry,
        LeaseEntry,
        RuntimeIdentityEntry,
        CorrectionEntry,
        ScopeCleanupEntry,
        EvidenceEntry,
        ResourceBinding,
        ResourcePlan,
        RuntimeLaunchRequest,
        RuntimeObservation,
        RuntimeCleanupReport,
        CleanupObservation,
        CredentialRequest,
        CredentialAdmission,
        CommandRequest,
        CommandResult,
        CancellationObservation,
        ModelCatalogSnapshot,
        SettlementView,
        SettlementResult,
        FailureObservation,
    )
    from laomedo.agents.errors import RunnerError
    from laomedo.host.leases.client import LeaseClient


class ControllerStream(Protocol):
    """Borrowed native I/O only: no close, container identity or credentials."""

    def write(self, data: bytes) -> None:
        """Write through the launched controller's bounded native stdin."""

    def read_line(self) -> Line | None:
        """Read a native channel-tagged line, or EOF; EOF is not completion."""


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


class BaseRuntimeResource(ABC):
    """One allocated resource in the shared runtime's dependency-ordered plan."""

    @property
    @abstractmethod
    def binding(self) -> ResourceBinding:
        """Expose typed dependency inputs; host-only secrets stay excluded."""

    @abstractmethod
    def close(self, cause: BaseException | None = None) -> CleanupObservation:
        """Close only this resource; return uncertainty without hiding the cause."""


class BaseAttemptDriver(ABC):
    """Interchangeable admitted execution, independent of native resource topology."""

    @abstractmethod
    def open_activity_attempt(self, context: AttemptContext) -> dict[str, JsonValue]:
        """Construct the provider's current baseline/record shape for journal writes."""

    @abstractmethod
    def run(
        self, request: AttemptRequest, journal: BaseAttemptJournal, stop: StopContext
    ) -> AttemptOutcome:
        """Execute Fresh/Resume, native turns and cleanup on the creator thread.

        Return an outcome for every failure after reservation/lease acquisition;
        retain settlement for every status with a surviving lease. Never freeze,
        mutate Agent records, substitute a model or fall back to Fresh on Resume.
        """


class BaseAttemptJournal(ABC):
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
        after freeze, never while the driver still owns the lease.
        """

    @abstractmethod
    def abort(
        self, view: SettlementView, failure: FailureObservation | None
    ) -> SettlementResult:
        """Resolve failed/cancelled/freeze-failed supervision, serialized by Agent.

        Agent converts escaping exceptions to verified=False. No frozen snapshot
        is required; leases retain their provider-specific finish/heartbeat policy.
        """


class BaseCredentialProvider(ABC):
    """Common credential admission; native refresh/probes remain provider-owned."""

    @abstractmethod
    def admit(self, request: CredentialRequest) -> CredentialAdmission:
        """Preserve native timing/identity; expose only explicit host launch material.

        No universal token borrowing or success-only release. Do not delete host
        login or claim unsupported validity/deadline constraints were enforced.
        """


class BaseCommandExecutor(ABC):
    """Claude/OpenCode isolated worker jobs; CodexExecServer is a separate role."""

    @abstractmethod
    def execute(self, request: CommandRequest) -> CommandResult:
        """Admit bounded work and distinguish exit from exact worker cleanup."""

    @abstractmethod
    def request_cancel(self) -> CancellationObservation:
        """Stop admission and signal owned jobs at existing provider timing."""

    @abstractmethod
    def shutdown(self) -> CleanupObservation:
        """Drain workers and close transport, preserving cleanup uncertainty."""


class BaseModelCatalog(ABC):
    """Common zero-turn discovery; native caching/admission stays composed."""

    @abstractmethod
    def discover(self, *, refresh: bool = False) -> ModelCatalogSnapshot:
        """Return advertised choices without inference or selection substitution."""


class BaseActivityProjector(ABC):
    """Read-time native interpretation, separate from live terminal evidence."""

    usage_first_payload: ClassVar[bool] = False

    @classmethod
    @abstractmethod
    def accepts(cls, events: list[dict]) -> bool:
        """Recognize unqualified receipts; explicit persisted provider wins."""

    @abstractmethod
    def project(
        self,
        events: list[dict],
        *,
        root_thread: str | None = None,
        model: str | None = None,
    ) -> ActivityProjection:
        """Project native provenance with unknown usage/cost distinct from zero."""


@runtime_checkable
class ContainerBuilder(Protocol):
    """Build an admitted Docker request; shared runtime performs allocation."""

    def __call__(self, bindings: Mapping[str, ResourceBinding]) -> ContainerSession:
        """Resolve earlier dependency bindings into a native session specification."""


@runtime_checkable
class OwnedResourceBuilder(Protocol):
    """Allocate a non-Docker broker/telemetry resource under shared rollback."""

    def __call__(self, bindings: Mapping[str, ResourceBinding]) -> BaseRuntimeResource:
        """Return one owned non-Docker resource with its exact close contract."""
