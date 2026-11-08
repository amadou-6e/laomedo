"""Behavioral provider extension contracts, separate from application interfaces."""

from abc import ABC, abstractmethod
from laomedo.agents.agents.base.models import (
    RuntimeObservation,
    CancellationObservation,
    CleanupObservation,
    CommandRequest,
    CommandResult,
    CredentialRequest,
    CredentialBinding,
    ModelCatalogSnapshot,
    RuntimeLaunch,
)
from laomedo.agents.activity.models import ActivityProjection


class BaseAgentRuntime(ABC):
    """Own exact process/session lifecycle; ACP communication remains composed."""

    @classmethod
    def start(cls, *args, **kwargs) -> RuntimeLaunch:
        """Construct the provider's configured scope and return an opaque owned handle.

        Only trusted host factories supply constructor arguments. Existing native
        startup/admission failures propagate; launch does not imply ACP readiness.
        """
        runtime = cls(*args, **kwargs)
        return RuntimeLaunch(runtime=runtime, observation=runtime.observe())

    @abstractmethod
    def observe(self) -> RuntimeObservation:
        """Read known process and native-session facts without launching a turn."""

    @abstractmethod
    def request_cancel(self) -> CancellationObservation:
        """Request interruption without claiming native acknowledgement or cleanup."""

    @abstractmethod
    async def shutdown(self) -> CleanupObservation:
        """Close owned resources or preserve provider's fail-closed cleanup error."""


class BaseCommandExecutor(ABC):
    """Execute one admitted command; HTTP and MCP only adapt this boundary."""

    @abstractmethod
    def execute(self, request: CommandRequest) -> CommandResult:
        """Apply native policy and deadline; report bounded output and exact cleanup."""

    @abstractmethod
    def shutdown(self) -> CleanupObservation:
        """Stop admission and reconcile only resources allocated by this executor."""


class BaseCredentialProvider(ABC):
    """Own native credential preparation, validity and borrowed-state release."""

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

    @abstractmethod
    def discover(self, *, refresh: bool = False) -> ModelCatalogSnapshot:
        """Discover or refresh choices; never change the caller's selected model."""


class BaseActivityProjector(ABC):
    """Interpret one provider's observations into canonical shared Activity values."""

    usage_first_payload = False

    @abstractmethod
    def project(self, events, *, root_thread=None, model=None) -> ActivityProjection:
        """Project observed evidence; absent usage or pricing remains unknown."""
