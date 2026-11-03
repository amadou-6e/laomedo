"""Work graph records; filtering never changes dependency analysis."""

from __future__ import annotations

from datetime import datetime
from functools import total_ordering
from hashlib import sha256
from pathlib import Path
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import JsonValue
from typing import Literal
from pydantic import model_validator
import json
from laomedo.work_graph.serialization import _canonical
import os
import tempfile


class WorkItem(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )

    key: str
    repository: str
    number: int
    url: str
    title: str
    body: str
    state: str
    updated_at: str
    labels: tuple[str, ...]
    blockers_complete: bool

    @model_validator(mode="after")
    def validate_invariants(self):
        if self.state not in {"OPEN", "CLOSED"}:
            raise ValueError("Unsupported source issue state")
        if (
            not self.key
            or self.number < 1
            or not self.repository
            or not self.updated_at
        ):
            raise ValueError("Incomplete work item identity or source marker")
        if not isinstance(self.labels, tuple) or self.labels != tuple(
            sorted(set(self.labels))
        ):
            raise ValueError("Labels must be an immutable sorted set")
        return self


@total_ordering
class Dependency(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )

    prerequisite: str
    dependent: str
    prerequisite_url: str
    dependent_url: str
    prerequisite_repository: str
    dependent_repository: str
    provenance: str = "github-native-blocker"

    def _order_key(self):
        return (
            self.prerequisite,
            self.dependent,
            self.prerequisite_url,
            self.dependent_url,
            self.prerequisite_repository,
            self.dependent_repository,
            self.provenance,
        )

    def __lt__(self, other):
        if not isinstance(other, Dependency):
            return NotImplemented
        return self._order_key() < other._order_key()


class GraphSnapshot(BaseModel):
    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )

    repository: str
    fetched_at: str
    source_complete: bool
    items: tuple[WorkItem, ...]
    dependencies: tuple[Dependency, ...]
    source_warnings: tuple[str, ...] = ()
    connector_version: str = "github-gh-v1"
    schema_version: int = 1

    @model_validator(mode="after")
    def validate_invariants(self):
        if self.schema_version != 1:
            raise ValueError("Unsupported snapshot schema")
        try:
            timestamp = datetime.fromisoformat(self.fetched_at)
        except ValueError:
            raise ValueError("Fetch timestamp must be a valid ISO timestamp") from None
        if timestamp.tzinfo is None:
            raise ValueError("Fetch timestamp must include a timezone")
        if not all(
            isinstance(value, tuple)
            for value in (self.items, self.dependencies, self.source_warnings)
        ):
            raise ValueError("Snapshot collections must be immutable tuples")
        if len({item.key for item in self.items}) != len(self.items):
            raise ValueError("Duplicate stable work item identity")
        if self.items != tuple(sorted(self.items, key=lambda item: item.key)):
            raise ValueError("Items must use canonical ordering")
        if self.dependencies != tuple(sorted(set(self.dependencies))):
            raise ValueError(
                "Dependencies must use canonical ordering without duplicates"
            )
        return self

    @property
    def snapshot_id(self) -> str:
        return (
            "sha256:"
            + sha256(_canonical(self.model_dump()).encode("utf-8")).hexdigest()
        )

    def to_dict(self) -> dict:
        return {**self.model_dump(), "snapshot_id": self.snapshot_id}

    @classmethod
    def from_dict(cls, payload: dict) -> "GraphSnapshot":
        data = dict(payload)
        expected = data.pop("snapshot_id")
        data["items"] = tuple(
            WorkItem(**{**item, "labels": tuple(item["labels"])})
            for item in data["items"]
        )
        data["dependencies"] = tuple(
            Dependency(**edge) for edge in data["dependencies"]
        )
        data["source_warnings"] = tuple(data["source_warnings"])
        snapshot = cls(**data)
        if expected != snapshot.snapshot_id:
            raise ValueError("Snapshot digest mismatch")
        return snapshot

    def save(self, directory: Path) -> Path:
        """Write a new immutable artifact; refuse conflicting existing bytes."""
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (self.snapshot_id.removeprefix("sha256:") + ".json")
        content = json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n"
        fd, pending_name = tempfile.mkstemp(
            prefix=".snapshot-", suffix=".tmp", dir=directory
        )
        pending = Path(pending_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(pending, path)
            except FileExistsError:
                if path.read_text(encoding="utf-8") != content:
                    raise ValueError("Existing snapshot artifact differs")
        finally:
            pending.unlink(missing_ok=True)
        return path

    def cycle_keys(self) -> frozenset[str]:
        """Iterative strongly connected components, including self loops."""
        keys = {item.key for item in self.items}
        forward = {key: set() for key in keys}
        reverse = {key: set() for key in keys}
        for edge in self.dependencies:
            if edge.prerequisite in keys and edge.dependent in keys:
                forward[edge.prerequisite].add(edge.dependent)
                reverse[edge.dependent].add(edge.prerequisite)
        visited, order = set(), []
        for root in sorted(keys):
            if root in visited:
                continue
            stack = [(root, False)]
            while stack:
                key, exiting = stack.pop()
                if exiting:
                    order.append(key)
                elif key not in visited:
                    visited.add(key)
                    stack.append((key, True))
                    stack.extend((neighbor, False) for neighbor in sorted(forward[key]))
        assigned, cyclic = set(), set()
        for root in reversed(order):
            if root in assigned:
                continue
            component, stack = set(), [root]
            while stack:
                key = stack.pop()
                if key in assigned:
                    continue
                assigned.add(key)
                component.add(key)
                stack.extend(reverse[key] - assigned)
            if len(component) > 1 or root in forward[root]:
                cyclic.update(component)
        return frozenset(cyclic)

    def readiness(self) -> dict[str, str]:
        """Source-based readiness is inspection data, not dispatch authorization."""
        items = {item.key: item for item in self.items}
        cyclic = self.cycle_keys()
        blockers = {key: set() for key in items}
        for edge in self.dependencies:
            if edge.dependent in blockers:
                blockers[edge.dependent].add(edge.prerequisite)
        result = {}
        for key, item in items.items():
            if item.state == "CLOSED":
                result[key] = "closed"
            elif key in cyclic:
                result[key] = "cyclic"
            elif not self.source_complete or not item.blockers_complete:
                result[key] = "unknown"
            elif any(blocker not in items for blocker in blockers[key]):
                result[key] = "unknown"
            elif any(items[blocker].state != "CLOSED" for blocker in blockers[key]):
                result[key] = "blocked"
            else:
                result[key] = "ready"
        return result

    def project(self, state: str = "all", labels: tuple[str, ...] = ()) -> dict:
        if state not in {"all", "open", "closed"}:
            raise ValueError("Invalid state filter")
        matches = tuple(
            item
            for item in self.items
            if (state == "all" or item.state.lower() == state)
            and (not labels or set(labels).intersection(item.labels))
        )
        keys = {item.key for item in matches}
        readiness = self.readiness()
        return {
            "snapshot_id": self.snapshot_id,
            "source_complete": self.source_complete,
            "source_warnings": self.source_warnings,
            "items": [
                dict(item.model_dump(), readiness=readiness[item.key])
                for item in matches
            ],
            "dependencies": [
                edge.model_dump()
                for edge in self.dependencies
                if edge.prerequisite in keys and edge.dependent in keys
            ],
            "context_dependencies": [
                edge.model_dump()
                for edge in self.dependencies
                if edge.dependent in keys and edge.prerequisite not in keys
            ],
        }


class RelevantWorkContent(BaseModel):
    """Selected work and transitive prerequisites, excluding fetch-time noise."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    repository: str = Field(description="Snapshot's admitted repository identity.")
    schema_version: int = Field(description="Existing graph schema version.")
    connector_version: str = Field(description="Existing source connector version.")
    source_complete: bool = Field(
        description="Whether the source attests complete dependency discovery."
    )
    items: list[WorkItem] = Field(
        description="Relevant immutable items in stable key order."
    )
    unresolved_keys: list[str] = Field(
        description="Sorted referenced keys absent from the snapshot."
    )
    edges: list[Dependency] = Field(
        description="Relevant dependency edges in existing canonical JSON order."
    )

    def to_payload(self) -> dict:
        """Preserve the canonical selected-content hash preimage."""
        return self.model_dump()


class WorkSnapshot(BaseModel):
    """Selected immutable source identity and the exact body digest."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    key: str = Field(description="Stable source work-item key.")
    repository: str = Field(description="Source owner/repository identity.")
    number: int = Field(description="Source repository-local item number.")
    url: str = Field(description="Existing source URL.")
    updated_at: str = Field(
        description="Existing source update marker, preserved verbatim."
    )
    body_digest: str = Field(
        description="Existing canonical hash of the selected body."
    )

    def to_payload(self) -> dict:
        """Serialize exactly the existing six-field work hash preimage."""
        return self.model_dump()


class WorkOverride(BaseModel):
    """One explicitly admitted open-prerequisite exception, never implicit authority."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    prerequisite: str = Field(description="Exact current open prerequisite key.")
    dependent: str = Field(description="Exact selected dependent work key.")
    rationale: str = Field(
        description="Existing nonempty caller explanation, preserving whitespace."
    )


class WorkLaunchBinding(BaseModel):
    """Related selected/frozen/current evidence after source and readiness admission."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    work_snapshot: WorkSnapshot = Field(
        description="Selected source identity and body digest."
    )
    work_snapshot_id: str = Field(
        description="Canonical identity of the work snapshot projection."
    )
    input_digest: str = Field(description="Existing work/body/graph input hash.")
    selected_graph_snapshot_id: str = Field(
        description="Explicitly selected frozen or refreshed graph identity."
    )
    authorization_graph_snapshot_id: str = Field(
        description="Current complete source graph used for authorization checks."
    )
    selected_content_digest: str = Field(
        description="Selected transitive relevant-content identity."
    )
    frozen_content_digest: str = Field(
        description="Original relevant-content identity."
    )
    authorization_content_digest: str = Field(
        description="Current relevant-content identity."
    )
    source_choice: Literal["unchanged", "pinned", "refreshed"] = Field(
        description="Existing explicit stale-source choice."
    )
    override: WorkOverride | None = Field(
        description="Admitted prerequisite exception, explicitly null when absent."
    )

    def to_payload(self) -> dict:
        """Return the existing grant callback and launch wire shape."""
        return self.model_dump()


class WorkGrantLimits(BaseModel):
    """Related execution limits already admitted by the local grant authority."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    timeout_seconds: int = Field(
        description="Existing admitted execution timeout in seconds."
    )
    max_turns: int = Field(
        description="Existing admitted turn limit; this refactor introduces no runtime cap."
    )


class WorkLaunchGrant(BaseModel):
    """Nonsecret grant response after transactional one-use redemption."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    grant_id: str = Field(
        description="Redeemed grant reference matched to selected work."
    )
    operator_authorized: bool = Field(
        description="Existing host principal check succeeded before construction."
    )
    work_key: str = Field(description="Exact work key bound by the redeemed grant.")
    graph_snapshot_id: str = Field(
        description="Graph snapshot explicitly reviewed when the grant was issued."
    )
    content_digest: str = Field(
        description="Selected content digest already matched during redemption."
    )
    runner: str = Field(description="Existing authorized runner identifier.")
    scope: str = Field(description="Existing authorized launch scope.")
    expires_at: str = Field(
        description="Previously checked grant expiry, preserving original spelling."
    )
    limits: WorkGrantLimits = Field(
        description="Previously admitted timeout and turn limits."
    )

    def to_payload(self) -> dict:
        """Preserve the existing callback shape; this value is not authority."""
        return self.model_dump()


class WorkGrantReference(BaseModel):
    """Safe CLI receipt for an issued local grant, without host principal data."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    grant_ref: str = Field(description="Issued one-use grant identity.")
    work_key: str = Field(description="Explicitly selected work item.")
    graph_snapshot_id: str = Field(description="Reviewed source graph identity.")
    content_digest: str = Field(description="Reviewed selected-content digest.")
    expires_at: str = Field(
        description="Admitted grant expiry in existing ISO spelling."
    )
    limits: WorkGrantLimits = Field(
        description="Admitted limits grouped internally and flat on the CLI wire."
    )

    def to_payload(self) -> dict:
        """Keep the existing seven-field flat CLI receipt."""
        return {**self.model_dump(exclude={"limits"}), **self.limits.model_dump()}


class WorkLaunchResult(BaseModel):
    """Safe local launch summary; journal and output retention stay with callers."""

    model_config = ConfigDict(
        strict=True, frozen=True, extra="forbid", hide_input_in_errors=True
    )
    run_id: str = Field(
        description="Workflow run identity returned by the existing stage."
    )
    trace_id: str = Field(description="Correlated retained trace identity.")
    status: str = Field(
        description="Existing workflow status, without inventing completion."
    )
    completion_basis: JsonValue = Field(
        description="Existing recorded completion explanation, including unknown/null."
    )
    evidence_complete: bool = Field(
        description="Existing boolean projection of retained evidence completeness."
    )
    dispatch_attempts: int = Field(
        description="Existing recorded dispatch attempt count."
    )
    output_present: bool = Field(
        description="Existing truthiness projection of the returned output."
    )
    graph_revision: str = Field(description="Frozen graph revision used for dispatch.")

    def to_payload(self) -> dict:
        """Return the existing eight-field local-launch response."""
        return self.model_dump()
