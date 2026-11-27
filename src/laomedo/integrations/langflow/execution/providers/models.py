"""Credential-free worker routing and strict private-pipe envelopes."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from laomedo.integrations.langflow.execution.worker.models import NativeGraphJob
from laomedo.agents.connections.models import GraphRunPlan


class ProviderNodeRoute(BaseModel):
    """A worker-local virtual address, carrying no host endpoint or account ID."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    vertex_id: str = Field(min_length=1, max_length=512)
    port: int = Field(ge=10000, le=65535)


class ProviderWorkerJob(NativeGraphJob):
    """One graph bootstrap; the host retains its actual admission capability."""

    version: Literal[2] = 2
    providers: tuple[ProviderNodeRoute, ...]
    public_issues: tuple[str, ...] = ()


class ProviderWorkerCall(BaseModel):
    """One serial request on an already job-bound private pipe."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    version: Literal[2] = 2
    request_id: int = Field(gt=0)
    action: Literal["http", "review", "issue"]
    vertex_id: str = Field(min_length=1, max_length=512)
    method: Literal["GET", "POST"] = "POST"
    path: str = Field(default="", max_length=256)
    body: dict | None = Field(default=None, repr=False)


class ProviderWorkerReply(BaseModel):
    """Correlated application data, with no host credentials or grant transport."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    version: Literal[2] = 2
    request_id: int = Field(gt=0)
    status: int = Field(ge=200, le=599)
    payload: dict = Field(repr=False)


class PublicIssueSelection(BaseModel):
    """Host-derived anonymous read selection; never a connection or write grant."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    vertex_id: str = Field(min_length=1, max_length=512)
    repository_url: str
    number: int = Field(gt=0)
    labels: tuple[str, ...] = ()
    state: Literal["open", "closed", "all"] = "all"


class PreparedProviderGraph(BaseModel):
    """Host-only approved selections beside a separately credential-free bootstrap."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")
    plan: GraphRunPlan = Field(exclude=True, repr=False)
    job: ProviderWorkerJob
    issues: tuple[PublicIssueSelection, ...] = ()
