"""Behavioral provider extension contracts, separate from application interfaces."""

from abc import ABC, abstractmethod
from concurrent.futures import TimeoutError as FutureTimeout
from copy import deepcopy
import threading
import time
from laomedo.agents.agents.base.models import (
    CancellationObservation,
    CleanupObservation,
    CommandRequest,
    CommandResult,
    CredentialRequest,
    CredentialBinding,
    CredentialMaterial,
    ModelCatalog,
    ProcessHealthObservation,
    IsolationObservation,
)


class BaseCommandExecutor(ABC):
    """Execute one admitted command; HTTP and MCP only adapt this boundary."""

    @abstractmethod
    def execute(self, request: CommandRequest) -> CommandResult:
        """Apply native policy and deadline; report bounded output and exact cleanup."""

    @abstractmethod
    def shutdown(self) -> CleanupObservation:
        """Stop admission and reconcile only resources allocated by this executor."""


class BaseInterruptibleCommandExecutor(BaseCommandExecutor):
    """Optional exact-worker interruption, distinct from closing an executor scope.

    Implementations own a native job cancellation signal. Persistent execution
    services whose command interruption belongs to native ACP do not claim this
    capability. No fallback cancels an unrelated controller or invents an ack.
    """

    @abstractmethod
    def request_cancel(self) -> CancellationObservation:
        """Stop admission and signal active owned jobs; acknowledgement stays unknown."""


class BaseSplitCommandExecutor(BaseCommandExecutor):
    """Optional persistent executor paired with a credential-bearing controller.

    A caller using this capability needs liveness of that persistent service and
    the native split-controller isolation gate, not merely a transient job result.
    """

    @abstractmethod
    def check_health(self) -> ProcessHealthObservation:
        """Observe exact persistent executor/reader liveness or fail closed."""

    @abstractmethod
    def assert_controller_isolated(self, controller) -> IsolationObservation:
        """Verify the actual native controller/executor gate, independent of health."""


class BaseCredentialProvider(ABC):
    """Own native credential preparation, validity and borrowed-state release."""

    def borrow(self) -> CredentialMaterial:
        """Prepare a native source and return a host-only borrowed binding.

        Volume/profile providers keep secrets in their native owner. Providers
        admitting inline host tokens override this projection; neither form
        transfers refresh ownership or revokes host credentials on release.
        """
        return CredentialMaterial(binding=self.prepare(CredentialRequest()))

    @abstractmethod
    def prepare(self, request: CredentialRequest) -> CredentialBinding:
        """Admit or refresh credentials under local policy; return public metadata only."""

    @abstractmethod
    def validate(self, request: CredentialRequest) -> CredentialBinding:
        """Recheck the selected identity and validity without inventing authentication."""

    @abstractmethod
    def release(self) -> CleanupObservation:
        """Release owned temporary state without deleting borrowed host credentials."""


class BaseModelCatalog(ABC):
    """Discover model choices without inference, preserving native cache policy."""

    include_model_names: bool = False
    """Whether the existing HTTP projection includes native display/alias names."""

    def __init__(self):
        """Own cache observation synchronization without native discovery effects."""
        self._lock = threading.Lock()
        self._cached = None
        self._pending = None

    def snapshot(self) -> ModelCatalog | None:
        """Copy last observed choices, including stale values, without refreshing.

        A missing catalogue remains None. This observation never substitutes a
        selection, certifies freshness or exposes mutable cached containers.
        """
        with self._lock:
            return (
                ModelCatalog.from_payload(deepcopy(self._cached[1]))
                if self._cached is not None
                else None
            )

    def wait_until_idle(self, *, timeout: float) -> bool:
        """Wait for observed discovery completion, not success or run admission.

        Serialized providers hold the lock through native discovery and cleanup.
        A provider sharing in-flight work publishes its Future under the same
        lock. Waiting for that Future preserves its native cleanup lifetime.
        Other work may start after this observation returns.
        """
        deadline = time.monotonic() + timeout
        if not self._lock.acquire(timeout=timeout):
            return False
        try:
            pending = self._pending
        finally:
            self._lock.release()
        if pending is not None:
            try:
                pending.result(timeout=max(0.0, deadline - time.monotonic()))
            except FutureTimeout:
                return pending.done()
            except Exception:
                # The discovery failed; completion does not certify its result.
                return True
        return True

    @abstractmethod
    def list_models(self, *, refresh: bool = False) -> ModelCatalog:
        """Discover or refresh choices; never change the caller's selected model."""
