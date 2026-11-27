"""Host-only per-profile runtime records; none carries GitHub authority."""

from threading import Event
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from laomedo.host.leases.client import LeaseClient
from laomedo.host.leases.models import ContainerIdentity


class NativeProfileInstance(BaseModel):
    """Host-only operational container lifetime, with no private GitHub authority."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)
    owner_id: UUID = Field(
        description="Authoritative profile selected by host browser admission."
    )
    container_id: str = Field(
        pattern=r"^[0-9a-f]{64}$",
        exclude=True,
        repr=False,
        description="Actual inspected immutable Docker ID used for private API calls.",
    )
    identity: ContainerIdentity = Field(
        exclude=True,
        repr=False,
        description="Exact owned container reservation, never a browser capability.",
    )
    volume: str = Field(
        exclude=True,
        repr=False,
        description="Verified deployment/owner-scoped local Docker volume.",
    )
    lease: LeaseClient = Field(
        exclude=True,
        repr=False,
        description="Independent supervisor registration for this container.",
    )
    cancelled: Event = Field(
        exclude=True,
        repr=False,
        description="Lease-loss and stop notification, unrelated to GitHub grants.",
    )
