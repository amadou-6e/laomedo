"""Private one-job process handoffs; capabilities are excluded from serialization."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from laomedo.github.node_runs.models import GitHubWorkerReadRequest
from laomedo.integrations.langflow.graph_admission.models import GitHubCatalogSnapshot


class GraphWorkerJob(BaseModel):
    """Host-approved bootstrap for exactly one isolated native graph process."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    version: Literal[1] = Field(default=1, description="Private pipe protocol version.")
    job_id: UUID = Field(description="Exact broker-admitted job identity.")
    flow_id: UUID = Field(description="Flow definition selected for this job.")
    graph: dict = Field(
        repr=False, description="Effective JSON graph approved on the host."
    )
    graph_digest: str = Field(
        pattern=r"^[0-9a-f]{64}$", description="Broker fingerprint of that exact graph."
    )
    catalog: GitHubCatalogSnapshot = Field(
        description="Immutable host code identities pinned to this admission."
    )
    capability: SecretStr = Field(
        exclude=True,
        repr=False,
        min_length=43,
        max_length=43,
        description="Job-only broker capability injected on the private pipe, not in graph data.",
    )
    inputs: list[dict[str, str]] = Field(
        default_factory=list,
        repr=False,
        description="Native graph inputs belonging only to this job.",
    )
    outputs: list[str] | None = Field(
        default=None,
        description="Explicit native output vertices, or all terminal outputs.",
    )
    timeout_seconds: float = Field(
        strict=True,
        gt=0,
        allow_inf_nan=False,
        description="Remaining real execution timeout in seconds, supplied by job policy.",
    )

    def private_payload(self):
        """Project the clear capability only for direct injection into this worker."""
        return {
            **self.model_dump(mode="json"),
            "capability": self.capability.get_secret_value(),
        }


class GraphWorkerCall(BaseModel):
    """One read-only broker request from an isolated graph process."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    version: Literal[1] = Field(default=1, description="Private pipe protocol version.")
    action: Literal["inspect"] = Field(
        default="inspect", description="Only the implemented read dispatcher."
    )
    request_id: int = Field(
        strict=True, gt=0, description="Serial per-channel reply correlation."
    )
    capability: SecretStr = Field(
        exclude=True,
        repr=False,
        min_length=43,
        max_length=43,
        description="Job-only authentication, never a GitHub credential.",
    )
    request: GitHubWorkerReadRequest = Field(
        description="Job/vertex selectors and read filters only."
    )

    def private_payload(self):
        """Project worker authentication only onto its private process channel."""
        return {
            **self.model_dump(mode="json"),
            "capability": self.capability.get_secret_value(),
        }


class GraphWorkerReply(BaseModel):
    """One correlated broker payload or fixed authorization failure."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    version: Literal[1] = Field(default=1, description="Private pipe protocol version.")
    request_id: int = Field(
        strict=True, gt=0, description="Request receiving this reply."
    )
    payload: dict | None = Field(
        default=None,
        repr=False,
        description="Authorized buffered node data, without tokens.",
    )
    code: (
        Literal[
            "github_node_authorization_unavailable", "github_graph_runtime_unavailable"
        ]
        | None
    ) = Field(
        default=None,
        description="Fixed safe failure; no provider or private-input diagnostics.",
    )

    @model_validator(mode="after")
    def one_outcome(self):
        """Refuse ambiguous success/error envelopes."""
        if (self.payload is None) == (self.code is None):
            raise ValueError("graph_worker_reply_invalid")
        return self


class GraphWorkerResult(BaseModel):
    """Terminal private outcome, separate from any confirmed external effect."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    version: Literal[1] = Field(default=1, description="Private pipe protocol version.")
    event: Literal["completed", "failed", "timed_out"] = Field(
        description="Terminal execution state of this worker only."
    )
    job_id: UUID = Field(description="Exact job producing this terminal message.")
    outputs: list[dict] | None = Field(
        default=None,
        repr=False,
        description="Native terminal outputs for owner-scoped release and history.",
    )
    code: Literal["github_graph_runtime_unavailable"] | None = Field(
        default=None, description="Fixed runtime failure without private diagnostics."
    )

    @model_validator(mode="after")
    def terminal_outcome(self):
        """Refuse failures presented as successful output or mixed outcomes."""
        if self.event == "completed":
            if self.outputs is None or self.code is not None:
                raise ValueError("graph_worker_result_invalid")
        elif self.outputs is not None or self.code is None:
            raise ValueError("graph_worker_result_invalid")
        return self
