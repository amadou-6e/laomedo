"""Assistant requests, declarative graphs and app-database-owned retained rows."""

import time
from typing import Literal
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field as ModelField,
    JsonValue,
    model_validator,
)
from sqlalchemy import Column, JSON, UniqueConstraint, Text
from sqlmodel import SQLModel, Field
from laomedo.agents.agents.base.models import NativeCommandInvocation


class AuthoringContext(BaseModel):
    """Host-only authority binding; none of these identities are MCP tool arguments."""

    model_config = ConfigDict(frozen=True)
    owner_id: UUID = ModelField(description="Authenticated application owner.")
    conversation_id: UUID = ModelField(
        description="Conversation permitted to own the new drafts."
    )
    message_id: UUID = ModelField(
        description="Exact active message behind these tools."
    )
    attempt_id: UUID = ModelField(description="Exact application dispatch attempt.")
    session_key: str = ModelField(
        exclude=True,
        repr=False,
        description="Host-only session fingerprint, never forwarded to the provider.",
    )


class ConversationRequest(BaseModel):
    """Choose initial defaults; creation never submits a prompt."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    provider: Literal["codex", "claude", "opencode"] = ModelField(
        default="codex",
        description="Immutable registered provider for this conversation.",
    )
    model: str = ModelField(
        min_length=1, max_length=256, description="Exact discovered model selection."
    )
    effort: str = ModelField(
        min_length=1, max_length=100, description="Supported reasoning selection."
    )
    linked_conversation_id: UUID | None = ModelField(
        default=None,
        description="Explicit predecessor when safe continuation is unavailable.",
    )


class ConversationRenameRequest(BaseModel):
    """A bounded explicit conversation title, independent of execution settings."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    title: str = ModelField(min_length=1, max_length=80)

    @model_validator(mode="after")
    def require_title(self):
        """Reject blank titles without altering the user's chosen name."""
        if not self.title.strip():
            raise ValueError("assistant_title_empty")
        return self


class MessageRequest(BaseModel):
    """One stable client key denotes exactly one user message and its attempt."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    client_message_id: UUID = ModelField(
        description="Caller-retained idempotency key; never regenerated after a lost response."
    )
    text: str = ModelField(
        min_length=1,
        max_length=12000,
        repr=False,
        description="User-authored prompt retained in private local history.",
    )
    model: str | None = ModelField(
        default=None,
        min_length=1,
        max_length=256,
        description="Discovered model for this turn; omitted uses conversation defaults.",
    )
    effort: str | None = ModelField(
        default=None,
        min_length=1,
        max_length=100,
        description="Supported effort for this turn; supplied together with model.",
    )

    @model_validator(mode="after")
    def require_text(self):
        """Refuse whitespace without silently altering the retained prompt."""
        if not self.text.strip():
            raise ValueError("assistant_message_empty")
        if (self.model is None) != (self.effort is None):
            raise ValueError("assistant_selection_incomplete")
        return self

    def digest(self):
        """Bind explicit selections to the stable key; preserve text-only callers' identity."""
        import hashlib
        import json

        payload = (
            self.text
            if self.model is None
            else json.dumps(
                [self.text, self.model, self.effort],
                ensure_ascii=True,
                separators=(",", ":"),
            )
        )
        return hashlib.sha256(payload.encode()).hexdigest()


class StopRequest(BaseModel):
    """Cancellation selects the exact active app attempt, never an arbitrary runner ID."""

    model_config = ConfigDict(extra="forbid")
    attempt_id: UUID = ModelField(
        description="Exact active application attempt to stop."
    )


class DraftNode(BaseModel):
    """An installed component identity, local node key and explicit static settings."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    key: str = ModelField(
        pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$",
        description="Graph-local node identity.",
    )
    component_type: str = ModelField(
        min_length=1,
        max_length=200,
        description="Canonical installed component identity returned by discovery.",
    )
    fields: dict[str, JsonValue] = ModelField(
        default_factory=dict,
        description="Only schema-approved, non-secret static settings; no code templates.",
    )


class DraftEdge(BaseModel):
    """An exact named output connected to an exact compatible input."""

    model_config = ConfigDict(extra="forbid")
    source: str = ModelField(max_length=64, description="Source node key.")
    output: str = ModelField(
        max_length=100, description="Installed output name, not its display label."
    )
    target: str = ModelField(max_length=64, description="Target node key.")
    input: str = ModelField(
        max_length=100, description="Installed input name, not its display label."
    )


class DraftGraph(BaseModel):
    """Bounded declarative graph; trusted templates are supplied exclusively by the host."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    nodes: list[DraftNode] = ModelField(
        min_length=1,
        max_length=40,
        description="Installed components to place on the editable canvas.",
    )
    edges: list[DraftEdge] = ModelField(
        default_factory=list,
        max_length=100,
        description="Exact named compatible connections.",
    )
    allow_incomplete: bool = ModelField(
        default=False,
        description="Explicitly retain missing required settings with incomplete diagnostics.",
    )


class WorkflowSource(BaseModel):
    """Bind an inspected source workflow to the revision observed by the assistant."""

    model_config = ConfigDict(extra="forbid")
    workflow_id: UUID = ModelField(
        description="Owner-visible saved source; it is never modified by this operation."
    )
    revision: str = ModelField(
        pattern=r"^sha256:[0-9a-f]{64}$",
        description="Exact source revision returned by get_workflow.",
    )


class DraftRequest(BaseModel):
    """Idempotent create or conditional edit of this conversation's own draft."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    draft_key: str = ModelField(
        pattern=r"^[A-Za-z0-9_-]{1,80}$",
        description="Operation key unique within the conversation; edits require a new key.",
    )
    name: str = ModelField(
        min_length=1, max_length=120, description="Human-readable saved workflow name."
    )
    spec: DraftGraph = ModelField(
        description="Declarative nodes and edges, never executable component JSON."
    )
    sources: list[WorkflowSource] = ModelField(
        default_factory=list,
        max_length=20,
        description="Exact inspected sources used for this operation.",
    )
    draft_id: UUID | None = ModelField(
        default=None,
        description="Existing draft owned by this conversation; source workflows cannot be updated.",
    )
    expected_revision: str | None = ModelField(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
        description="Required exact current revision for an assistant edit.",
    )

    @model_validator(mode="after")
    def paired_revision(self):
        """Refuse unconditional edits and revisions without a target."""
        if (self.draft_id is None) != (self.expected_revision is None):
            raise ValueError("assistant_revision_required")
        return self


class AssistantSession(SQLModel, table=True):
    """Retained revocation fence for a validated application session; no bearer is stored."""

    __tablename__ = "laomedo_assistant_session"
    key: str = Field(
        primary_key=True,
        description="SHA256 fingerprint of the already authenticated app session.",
    )
    owner_id: UUID = Field(
        index=True, description="Authenticated owner of this session."
    )
    expires_at: float = Field(description="Validated session expiry as Unix seconds.")
    revoked: bool = Field(
        default=False,
        description="Logout/lock prevents future chat dispatch and tool effects.",
    )


class AssistantConversation(SQLModel, table=True):
    """Application-owned identity and current native binding, excluding credentials."""

    __tablename__ = "laomedo_assistant_conversation"
    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        description="Durable conversation identity.",
    )
    owner_id: UUID = Field(
        index=True, description="Authenticated owner; never model-selectable."
    )
    provider: str = Field(description="Fixed provider selection.")
    model: str = Field(
        description="Latest admitted native model selection; default for the next turn."
    )
    effort: str = Field(
        description="Latest admitted reasoning selection; default for the next turn."
    )
    title: str = Field(
        default="New conversation", description="Bounded first-message preview."
    )
    state: str = Field(
        default="idle",
        description="Application state including reconciliation and blocked continuation.",
    )
    active_message_id: UUID | None = Field(
        default=None,
        description="Single reserved/active message under the database lock.",
    )
    run_id: str | None = Field(
        default=None, description="Existing dedicated runner invocation identity."
    )
    runner_instance_id: str | None = Field(
        default=None,
        description="Observed runner instance; restart cannot silently replace a session.",
    )
    thread_id: str | None = Field(
        default=None, description="Observed existing native session."
    )
    workspace_hash: str | None = Field(
        default=None,
        description="Observed safe workspace checkpoint used for the next distinct prompt.",
    )
    error_code: str | None = Field(
        default=None,
        description="Stable safe explanation when continuation is blocked.",
    )
    linked_conversation_id: UUID | None = Field(
        default=None,
        description="Explicit predecessor; starting anew never erases history.",
    )
    created_at: float = Field(
        default_factory=time.time, description="Creation time as Unix seconds."
    )
    updated_at: float = Field(
        default_factory=time.time,
        index=True,
        description="Most recent retained conversation change.",
    )


class AssistantMessage(SQLModel, table=True):
    """A durable prompt, dispatch reservation and final safe display outcome."""

    __tablename__ = "laomedo_assistant_message"
    native_action_id: UUID | None = Field(
        default=None,
        description="Approved native command receipt, absent for ordinary user prompts.",
    )
    __table_args__ = (UniqueConstraint("conversation_id", "client_message_id"),)
    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        description="Durable app message identity.",
    )
    conversation_id: UUID = Field(index=True, description="Owning conversation.")
    client_message_id: UUID = Field(description="Stable caller idempotency key.")
    attempt_id: UUID = Field(
        default_factory=uuid4,
        description="Stable application attempt; subsequent prompts also use this as native Activity identity.",
    )
    digest: str = Field(description="Canonical semantic request digest.")
    model: str | None = Field(
        default=None,
        description="Immutable admitted model for this turn; absent on earlier retained rows.",
    )
    effort: str | None = Field(
        default=None,
        description="Immutable admitted reasoning effort for this turn; absent on earlier retained rows.",
    )
    stop_requested: bool = Field(
        default=False,
        description="Durable cancellation intent, including dispatch whose response was lost.",
    )
    activity_snapshot: dict | None = Field(
        default=None,
        sa_column=Column(JSON),
        description="Last validated normalized Activity page; private retained display works without a running provider.",
    )
    text: str = Field(
        sa_column=Column(Text, nullable=False),
        description="Private retained user prompt.",
    )
    state: str = Field(
        default="reserved",
        description="Observed dispatch/terminal/uncertain state, never inferred replay permission.",
    )
    run_id: str | None = Field(
        default=None, description="Observed native invocation identity."
    )
    native_attempt_id: str | None = Field(
        default=None,
        description="Observed native Activity identity; initial runs allocate this inside the runner.",
    )
    response: str | None = Field(
        default=None,
        sa_column=Column(Text),
        description="Retained final assistant text; partial content remains in Activity.",
    )
    error_code: str | None = Field(
        default=None, description="Allowlisted safe failure category."
    )
    created_at: float = Field(
        default_factory=time.time, description="Prompt reservation time."
    )


class AssistantDraftReceipt(SQLModel, table=True):
    """Atomic evidence of a saved Flow, independent of the model's later outcome."""

    __tablename__ = "laomedo_assistant_draft_receipt"
    __table_args__ = (UniqueConstraint("conversation_id", "draft_key"),)
    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        description="Authoritative persisted save receipt.",
    )
    owner_id: UUID = Field(index=True, description="Authenticated tool owner.")
    conversation_id: UUID = Field(
        index=True, description="Conversation whose drafts this tool may modify."
    )
    message_id: UUID = Field(description="User message responsible for this save.")
    attempt_id: UUID = Field(description="Native attempt responsible for this save.")
    draft_key: str = Field(description="Idempotent operation key.")
    digest: str = Field(description="Canonical operation digest.")
    workflow_id: UUID = Field(
        index=True, description="Ordinary persisted Langflow Flow identity."
    )
    name: str = Field(description="Name recorded when this save committed.")
    revision: str = Field(description="Exact saved Flow revision.")
    diagnostics: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON),
        description="Explicit structural incompleteness; never an execution success claim.",
    )
    created_at: float = Field(
        default_factory=time.time, description="Atomic save time."
    )


class GraphFieldUpdate(BaseModel):
    """Explicit static field replacements on one existing saved node."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    node_id: str = ModelField(min_length=1, max_length=200)
    fields: dict[str, JsonValue] = ModelField(min_length=1, max_length=40)


class GraphConnection(BaseModel):
    """Named compatible ports on exact saved or newly added node IDs."""

    model_config = ConfigDict(extra="forbid")
    source: str = ModelField(min_length=1, max_length=200)
    output: str = ModelField(min_length=1, max_length=100)
    target: str = ModelField(min_length=1, max_length=200)
    input: str = ModelField(min_length=1, max_length=100)


class GraphChanges(BaseModel):
    """A bounded explicit patch; absence never means delete an unmentioned setting."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    name: str | None = ModelField(default=None, min_length=1, max_length=120)
    updates: list[GraphFieldUpdate] = ModelField(default_factory=list, max_length=40)
    add_nodes: list[DraftNode] = ModelField(default_factory=list, max_length=40)
    remove_nodes: list[str] = ModelField(default_factory=list, max_length=40)
    connect: list[GraphConnection] = ModelField(default_factory=list, max_length=100)
    disconnect: list[GraphConnection] = ModelField(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def require_change(self):
        """Refuse empty/no-name proposals without silently inventing a mutation."""
        if not any(
            (
                self.name,
                self.updates,
                self.add_nodes,
                self.remove_nodes,
                self.connect,
                self.disconnect,
            )
        ):
            raise ValueError("assistant_graph_change_empty")
        if self.name is not None and not self.name.strip():
            raise ValueError("assistant_title_empty")
        if len(self.model_dump_json().encode()) > 65536:
            raise ValueError("assistant_graph_too_large")
        return self


class GraphActionRequest(BaseModel):
    """Exact immutable proposal semantics; it grants no execution authority."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    operation_key: str = ModelField(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    workflow_id: UUID
    expected_revision: str = ModelField(pattern=r"^sha256:[0-9a-f]{64}$")
    kind: Literal["edit", "run"]
    summary: str = ModelField(default="", max_length=240)
    changes: GraphChanges | None = None
    input_value: str = ModelField(default="", max_length=12000, repr=False)
    input_type: Literal["chat", "text", "any"] = "chat"
    output_type: Literal["chat", "text", "any", "debug"] = "any"

    @model_validator(mode="after")
    def require_kind_arguments(self):
        """Forbid silently ignored edit/run arguments and ambiguous digests."""
        if (self.kind == "edit") != (self.changes is not None):
            raise ValueError("assistant_action_arguments_invalid")
        if self.kind == "edit" and (
            self.input_value or self.input_type != "chat" or self.output_type != "any"
        ):
            raise ValueError("assistant_action_arguments_invalid")
        return self

    @property
    def category(self):
        """Derive approval scope from actual changes, never from model wording."""
        if self.kind == "run":
            return "run"
        changes = self.changes
        if (
            changes
            and changes.name is not None
            and not any(
                (
                    changes.updates,
                    changes.add_nodes,
                    changes.remove_nodes,
                    changes.connect,
                    changes.disconnect,
                )
            )
        ):
            return "rename"
        return "edit"

    def digest(self):
        """Bind every proposal field, including target revision and execution inputs."""
        import hashlib
        import json

        return hashlib.sha256(
            json.dumps(
                self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()


class GraphActionDecision(BaseModel):
    """Human app-only decision; not present in the provider MCP manifest."""

    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "always_approve", "reject"]
    digest: str = ModelField(pattern=r"^[0-9a-f]{64}$")


class AssistantGraphAction(SQLModel, table=True):
    """Durable proposal, human decision and effect observation; no raw graph snapshot."""

    __tablename__ = "laomedo_assistant_graph_action"
    __table_args__ = (UniqueConstraint("conversation_id", "operation_key"),)
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    owner_id: UUID = Field(index=True)
    conversation_id: UUID = Field(index=True)
    message_id: UUID
    attempt_id: UUID
    session_key: str = Field(repr=False)
    operation_key: str
    workflow_id: UUID
    name: str
    kind: str
    digest: str
    request: dict = Field(sa_column=Column(JSON), repr=False)
    preview: list[str] = Field(sa_column=Column(JSON))
    state: str = "pending"
    revision: str
    result_revision: str | None = None
    run_id: UUID | None = None
    error_code: str | None = None
    created_at: float = Field(default_factory=time.time)
    expires_at: float

    def public(self, *, session_key=None):
        """Project safe outcome and optional current human-session decision availability."""
        import time

        result = self.model_dump(
            mode="json", exclude={"owner_id", "session_key", "request"}
        )
        request = GraphActionRequest.model_validate(self.request)
        result["category"] = request.category
        result["summary"] = request.summary.strip()
        result["new_name"] = (
            request.changes.name if request.category == "rename" else None
        )
        if self.state == "pending" and self.expires_at <= time.time():
            result["state"] = "expired"
        if session_key is not None:
            result["can_decide"] = (
                self.session_key == session_key and result["state"] == "pending"
            )
        return result


class NativeCommandRequest(NativeCommandInvocation):
    """Idempotent proposal for one exact built-in native command."""

    operation_key: str = ModelField(
        min_length=1,
        max_length=80,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Stable proposal key reused after uncertain acknowledgements.",
    )

    def digest(self):
        """Bind the exact command, arguments, catalog and operation key."""
        import hashlib
        import json

        return hashlib.sha256(
            json.dumps(
                self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()


class NativeActionDecision(BaseModel):
    """Human-only explicit native command decision; no persistent grant."""

    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"] = ModelField(
        description="Human approval or rejection of the exact displayed native command."
    )
    digest: str = ModelField(
        pattern=r"^[0-9a-f]{64}$",
        description="Exact proposal digest bound to this human decision.",
    )


class AssistantNativeAction(SQLModel, table=True):
    """Owner-scoped command proposal atomically linked to its reserved message."""

    __tablename__ = "laomedo_assistant_native_action"
    __table_args__ = (UniqueConstraint("conversation_id", "operation_key"),)
    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        description="Host-generated proposal identity.",
    )
    owner_id: UUID = Field(index=True, description="Authenticated app owner.")
    conversation_id: UUID = Field(
        index=True, description="Conversation to which this permission is confined."
    )
    message_id: UUID = Field(
        description="Assistant response that originated the proposal."
    )
    session_key: str = Field(
        repr=False, description="Originating human app session binding."
    )
    operation_key: str = Field(
        description="Conversation-scoped proposal idempotency key."
    )
    digest: str = Field(description="Exact proposed operation digest.")
    request: dict = Field(
        sa_column=Column(JSON),
        repr=False,
        description="Validated native command proposal, containing no credentials.",
    )
    run_id: str = Field(
        repr=False, description="Existing owned runner execution binding."
    )
    thread_id: str = Field(repr=False, description="Existing native session binding.")
    state: str = Field(
        default="pending",
        description="Pending, executing or retained terminal/unknown outcome.",
    )
    result_message_id: UUID | None = Field(
        default=None, description="Atomically reserved command message identity."
    )
    created_at: float = Field(
        default_factory=time.time, description="Creation timestamp in Unix seconds."
    )
    expires_at: float = Field(description="Human approval deadline in Unix seconds.")

    def public(self, *, session_key=None):
        """Return a compact safe approval receipt, never native dispatch authority."""
        request = NativeCommandRequest.model_validate(self.request)
        state = (
            "expired"
            if self.state == "pending" and self.expires_at <= time.time()
            else self.state
        )
        return {
            "id": str(self.id),
            "message_id": str(self.message_id),
            "name": request.name,
            "arguments": request.arguments,
            "digest": self.digest,
            "state": state,
            "may_use_model": request.name in {"review", "compact"},
            "can_decide": session_key == self.session_key and state == "pending",
            "result_message_id": (
                str(self.result_message_id) if self.result_message_id else None
            ),
        }


class AssistantGraphPermission(SQLModel, table=True):
    """Human consent for one category across a conversation, never provider authority."""

    __tablename__ = "laomedo_assistant_graph_permission"
    __table_args__ = (UniqueConstraint("conversation_id", "session_key", "category"),)
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    owner_id: UUID = Field(index=True)
    conversation_id: UUID = Field(index=True)
    session_key: str = Field(repr=False)
    category: str
    action_id: UUID
    created_at: float = Field(default_factory=time.time)
