"""One isolated gateway case shared by this concern's controls."""

from pydantic import BaseModel, ConfigDict, Field
from laomedo.host.mediation.store import MediationStore
from laomedo.github.transport.rest import GitHubRestTransport
from laomedo.github.issues.gateway import GitHubIssueGateway


class IssueCase(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    clock: list[float] = Field(description="Mutable deterministic test clock.")
    store: MediationStore = Field(description="Isolated durable mediation store.")
    provider: object = Field(
        description="Internal provider double; never live acceptance."
    )
    transport: GitHubRestTransport = Field(
        description="Actual production REST adapter."
    )
    binding: dict[str, str] = Field(description="Synthetic test grant binding.")
    gateway: GitHubIssueGateway = Field(
        description="Actual production resource gateway."
    )
    url: str = Field(description="Repository URL for this case.")
    grant_id: str = Field(description="Synthetic grant identifier owned by this case.")
