"""Synthetic GitHub source pages for EXP-16, separate from the package tests."""

from copy import deepcopy

REPOSITORY = "verify/exp16"
FETCHED_AT = "2026-10-05T10:00:00+00:00"
NOW = "2026-10-05T10:00:00+00:00"
SELECTED = "github:S-20"
PREREQUISITE = "github:C-10"


def ref(identifier, repository=REPOSITORY):
    return {"id": identifier,
            "url": f"https://github.com/{repository}/issues/{identifier.split('-')[-1]}",
            "repository": {"nameWithOwner": repository}}


def node(identifier, number, state="OPEN", *, body="Synthetic task.", labels=(),
         blocked_by=(), blocker_count=None):
    return {"id": identifier, "number": number,
            "url": f"https://github.com/{REPOSITORY}/issues/{number}",
            "title": f"Fixture {identifier}", "body": body, "state": state,
            "updatedAt": "2026-10-05T09:00:00Z",
            "labels": {"totalCount": len(labels),
                       "nodes": [{"name": value} for value in labels]},
            "blockedBy": {"totalCount": len(blocked_by) if blocker_count is None else blocker_count,
                          "nodes": list(blocked_by)},
            "blocking": {"totalCount": 0, "nodes": []}}


def page(nodes):
    return [{"data": {"repository": {"nameWithOwner": REPOSITORY,
        "issues": {"totalCount": len(nodes),
                   "pageInfo": {"hasNextPage": False, "endCursor": None},
                   "nodes": nodes}}}}]


def corpus():
    closed = node("C-10", 10, "CLOSED")
    selected = node("S-20", 20, labels=("work",), blocked_by=(ref("C-10"),))
    base = page([closed, selected, node("I-30", 30)])
    content = deepcopy(base)
    content[0]["data"]["repository"]["issues"]["nodes"][1]["body"] = "Changed task body."
    content[0]["data"]["repository"]["issues"]["nodes"][1]["updatedAt"] = "2026-10-05T09:30:00Z"
    opened = deepcopy(base)
    opened[0]["data"]["repository"]["issues"]["nodes"][0]["state"] = "OPEN"
    unresolved = deepcopy(base)
    unresolved[0]["data"]["repository"]["issues"]["nodes"][1]["blockedBy"] = {
        "totalCount": 1, "nodes": [ref("E-77", "other/private")]}
    cycle = deepcopy(opened)
    cycle[0]["data"]["repository"]["issues"]["nodes"][0]["blockedBy"] = {
        "totalCount": 1, "nodes": [ref("S-20")]}
    incomplete = deepcopy(base)
    incomplete[0]["data"]["repository"]["issues"]["nodes"][1]["blockedBy"]["totalCount"] = 2
    return {"base": base, "content_changed": content, "opened_blocker": opened,
            "unresolved_external": unresolved, "cycle": cycle,
            "incomplete": incomplete}
