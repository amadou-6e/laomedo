"""Read-only native GitHub dependencies through the user's existing gh login."""

from datetime import datetime, timezone
import json
import re
import subprocess
from typing import Callable

from .model import Dependency, GraphSnapshot, WorkItem


QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    nameWithOwner
    issues(first: 100, after: $cursor, orderBy: {field: CREATED_AT, direction: ASC}) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        id number url title body state updatedAt
        labels(first: 100) { totalCount nodes { name } }
        blockedBy(first: 100) {
          totalCount nodes { id url repository { nameWithOwner } }
        }
        blocking(first: 100) {
          totalCount nodes { id url repository { nameWithOwner } }
        }
      }
    }
  }
}
"""


def validate_repository(repository: str) -> tuple[str, str]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Repository must be owner/name")
    return tuple(repository.split("/"))


def _gh_page(owner: str, name: str, cursor: str | None) -> dict:
    command = ["gh", "api", "graphql", "-f", f"query={QUERY}",
               "-f", f"owner={owner}", "-f", f"name={name}"]
    if cursor is not None:
        command.extend(["-f", f"cursor={cursor}"])
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=60)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("GitHub fetch timed out") from error
    # gh stderr may contain account or transport detail; it is not snapshot data.
    if result.returncode:
        raise RuntimeError("GitHub fetch failed; check gh authentication and connectivity")
    return json.loads(result.stdout)


def _connection(page: dict, repository: str) -> dict | None:
    source = (page.get("data") or {}).get("repository")
    if not source:
        return None
    if source["nameWithOwner"].lower() != repository.lower():
        raise ValueError("GitHub response repository does not match request")
    return source.get("issues")


def fetch(repository: str, request: Callable = _gh_page) -> GraphSnapshot:
    owner, name = validate_repository(repository)
    pages, seen, cursor = [], set(), None
    while True:
        try:
            page = request(owner, name, cursor)
        except (RuntimeError, OSError):
            if not pages:
                raise
            pages.append({"errors": [{"message": "fetch_interrupted"}]})
            break
        pages.append(page)
        connection = _connection(page, repository)
        if connection is None or page.get("errors"):
            break
        info = connection["pageInfo"]
        if not info["hasNextPage"]:
            break
        cursor = info["endCursor"]
        if not cursor or cursor in seen:
            raise ValueError("GitHub pagination cursor missing or repeated")
        seen.add(cursor)
    return import_pages(repository, pages)


def import_pages(repository: str, pages: list[dict], fetched_at: str | None = None) -> GraphSnapshot:
    """Import captured GraphQL pages without credentials or network access."""
    validate_repository(repository)
    fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()
    if datetime.fromisoformat(fetched_at).tzinfo is None:
        raise ValueError("Fetch timestamp must include a timezone")
    items, edges, counts, cursors, warnings = {}, {}, set(), set(), set()
    complete = bool(pages)
    finished = False
    for page in pages:
        if finished:
            raise ValueError("Unexpected page after terminal GitHub page")
        if page.get("errors"):
            complete = False
            warnings.add("fetch_error")
        connection = _connection(page, repository)
        if connection is None:
            complete = False
            warnings.add("unavailable_source")
            continue
        counts.add(connection["totalCount"])
        info = connection["pageInfo"]
        finished = not info["hasNextPage"]
        if not finished:
            cursor = info["endCursor"]
            if not cursor or cursor in cursors:
                raise ValueError("GitHub pagination cursor missing or repeated")
            cursors.add(cursor)
        for node in connection["nodes"]:
            if node is None:
                complete = False
                warnings.add("unavailable_item")
                continue
            key = "github:" + node["id"]
            labels = node["labels"]
            if labels["totalCount"] != len(labels["nodes"]):
                complete = False
                warnings.add("labels_incomplete")
            blockers = node["blockedBy"]
            item = WorkItem(
                key, repository, node["number"], node["url"], node["title"], node["body"],
                node["state"], node["updatedAt"],
                tuple(sorted({label["name"] for label in labels["nodes"]})),
                blockers["totalCount"] == len(blockers["nodes"]),
            )
            if key in items:
                # Concurrent updates or repeated pages prevent a coherent source snapshot.
                complete = False
                warnings.add("repeated_item")
                if items[key] != item:
                    raise ValueError("Conflicting snapshots for one GitHub issue")
            items[key] = item
            for relation in ("blockedBy", "blocking"):
                connection_edges = node[relation]
                if connection_edges["totalCount"] != len(connection_edges["nodes"]):
                    complete = False
                    warnings.add("dependencies_incomplete")
                for ref in connection_edges["nodes"]:
                    if not ref:
                        complete = False
                        warnings.add("unavailable_dependency")
                        continue
                    other = "github:" + ref["id"]
                    prerequisite, dependent = (other, key) if relation == "blockedBy" else (key, other)
                    urls = (ref["url"], item.url) if relation == "blockedBy" else (item.url, ref["url"])
                    repositories = (ref["repository"]["nameWithOwner"], repository)
                    if relation == "blocking":
                        repositories = repositories[::-1]
                    edge = Dependency(prerequisite, dependent, *urls, *repositories)
                    pair = (prerequisite, dependent)
                    if pair in edges and edges[pair] != edge:
                        raise ValueError("Conflicting dependency identities")
                    edges[pair] = edge
    if not finished:
        warnings.add("pagination_incomplete")
    if counts != {len(items)}:
        warnings.add("item_count_mismatch")
    complete = complete and finished and counts == {len(items)}
    return GraphSnapshot(repository, fetched_at, complete,
                         tuple(sorted(items.values(), key=lambda item: item.key)),
                         tuple(sorted(edges.values())), tuple(sorted(warnings)))
