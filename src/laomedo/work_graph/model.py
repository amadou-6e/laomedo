"""Work graph records; filtering never changes dependency analysis."""

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class WorkItem:
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

    def __post_init__(self) -> None:
        if self.state not in {"OPEN", "CLOSED"}:
            raise ValueError("Unsupported source issue state")
        if not self.key or self.number < 1 or not self.repository or not self.updated_at:
            raise ValueError("Incomplete work item identity or source marker")
        if not isinstance(self.labels, tuple) or self.labels != tuple(sorted(set(self.labels))):
            raise ValueError("Labels must be an immutable sorted set")


@dataclass(frozen=True, order=True)
class Dependency:
    prerequisite: str
    dependent: str
    prerequisite_url: str
    dependent_url: str
    prerequisite_repository: str
    dependent_repository: str
    provenance: str = "github-native-blocker"


@dataclass(frozen=True)
class GraphSnapshot:
    repository: str
    fetched_at: str
    source_complete: bool
    items: tuple[WorkItem, ...]
    dependencies: tuple[Dependency, ...]
    source_warnings: tuple[str, ...] = ()
    connector_version: str = "github-gh-v1"
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported snapshot schema")
        if datetime.fromisoformat(self.fetched_at).tzinfo is None:
            raise ValueError("Fetch timestamp must include a timezone")
        if not all(isinstance(value, tuple) for value in
                   (self.items, self.dependencies, self.source_warnings)):
            raise ValueError("Snapshot collections must be immutable tuples")
        if len({item.key for item in self.items}) != len(self.items):
            raise ValueError("Duplicate stable work item identity")
        if self.items != tuple(sorted(self.items, key=lambda item: item.key)):
            raise ValueError("Items must use canonical ordering")
        if self.dependencies != tuple(sorted(set(self.dependencies))):
            raise ValueError("Dependencies must use canonical ordering without duplicates")

    @property
    def snapshot_id(self) -> str:
        return "sha256:" + sha256(_canonical(asdict(self)).encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        return {**asdict(self), "snapshot_id": self.snapshot_id}

    @classmethod
    def from_dict(cls, payload: dict) -> "GraphSnapshot":
        data = dict(payload)
        expected = data.pop("snapshot_id")
        data["items"] = tuple(
            WorkItem(**{**item, "labels": tuple(item["labels"])}) for item in data["items"]
        )
        data["dependencies"] = tuple(Dependency(**edge) for edge in data["dependencies"])
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
        try:
            with path.open("x", encoding="utf-8") as stream:
                stream.write(content)
        except FileExistsError:
            if path.read_text(encoding="utf-8") != content:
                raise ValueError("Existing snapshot artifact differs")
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
            item for item in self.items
            if (state == "all" or item.state.lower() == state)
            and (not labels or set(labels).intersection(item.labels))
        )
        keys = {item.key for item in matches}
        readiness = self.readiness()
        return {
            "snapshot_id": self.snapshot_id,
            "source_complete": self.source_complete,
            "source_warnings": self.source_warnings,
            "items": [dict(asdict(item), readiness=readiness[item.key]) for item in matches],
            "dependencies": [asdict(edge) for edge in self.dependencies
                             if edge.prerequisite in keys and edge.dependent in keys],
            "context_dependencies": [asdict(edge) for edge in self.dependencies
                                     if edge.dependent in keys and edge.prerequisite not in keys],
        }
