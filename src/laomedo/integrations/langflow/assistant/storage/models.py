"""Canonical project storage configuration and bounded file requests."""

from uuid import UUID
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from laomedo.integrations.langflow.assistant.models import DraftGraph, DraftNode


class RepositoryRegistration(BaseModel):
    """An explicit host selection, never accepted from model tools."""

    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    path: str = Field(min_length=1, max_length=2000)


class RepositoryConnection(RepositoryRegistration):
    """One profile's verified local checkout."""

    id: UUID


class RepositoryLocation(BaseModel):
    """A relative file or directory within one registered checkout."""

    model_config = ConfigDict(extra="forbid")
    repository_id: UUID
    path: str = Field(min_length=1, max_length=500)


class GraphFileBinding(BaseModel):
    """A graph's selected location and last synchronized file digest."""

    location: RepositoryLocation
    sha256: str


class StorageDocument(BaseModel):
    """Profile-owned configuration persisted outside repositories."""

    repositories: list[RepositoryConnection] = Field(default_factory=list)
    agent_files: RepositoryLocation | None = None
    graphs: dict[str, GraphFileBinding] = Field(default_factory=dict)


class GraphFileRequest(BaseModel):
    """Explicit graph synchronization against observed app and file revisions."""

    model_config = ConfigDict(extra="forbid")
    location: RepositoryLocation
    expected_graph_revision: str = Field(min_length=1, max_length=100)
    expected_file_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class AgentFileWrite(BaseModel):
    """Create an absent text file or replace its exact observed contents."""

    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=500)
    content: str = Field(max_length=65536)
    expected_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class PortableGraphDefinition(DraftGraph):
    """The authoring contract also permits saving an empty editor canvas."""

    nodes: list[DraftNode] = Field(default_factory=list, max_length=40)


class PortableGraph(BaseModel):
    """Secret-free graph definition plus existing node identities for safe restoration."""

    model_config = ConfigDict(extra="forbid")
    format: Literal["laomedo.graph.v1"] = "laomedo.graph.v1"
    workflow_id: UUID
    name: str = Field(max_length=500)
    spec: PortableGraphDefinition
    node_ids: dict[str, str] = Field(max_length=40)
