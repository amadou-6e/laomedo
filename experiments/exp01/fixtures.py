"""Synthetic GraphQL responses for EXP-01, independent of package test fixtures."""

REPOSITORY = "verify/exp01"
FETCHED_AT = "2026-10-05T00:00:00+00:00"


def ref(identifier, repository=REPOSITORY):
    return {
        "id": identifier,
        "url": f"https://github.com/{repository}/issues/{identifier.split('-')[-1]}",
        "repository": {"nameWithOwner": repository},
    }


def node(identifier, number, state="OPEN", *, labels=(), body="",
         blocked_by=(), blocking=(), blocker_count=None, label_count=None):
    return {
        "id": identifier,
        "number": number,
        "url": f"https://github.com/{REPOSITORY}/issues/{number}",
        "title": f"Fixture {identifier}",
        "body": body,
        "state": state,
        "updatedAt": "2026-10-04T10:00:00Z",
        "labels": {"totalCount": len(labels) if label_count is None else label_count,
                   "nodes": [{"name": label} for label in labels]},
        "blockedBy": {"totalCount": len(blocked_by) if blocker_count is None else blocker_count,
                      "nodes": list(blocked_by)},
        "blocking": {"totalCount": len(blocking), "nodes": list(blocking)},
    }


def page(nodes, count, *, more=False, cursor=None):
    return {"data": {"repository": {"nameWithOwner": REPOSITORY,
        "issues": {"totalCount": count,
                   "pageInfo": {"hasNextPage": more, "endCursor": cursor},
                   "nodes": nodes}}}}


def corpus():
    closed = node("P-101", 101, "CLOSED", blocking=(ref("P-909"),))
    dependent = node("P-909", 909, labels=("focus",), blocked_by=(ref("P-101"),))
    isolated = node("P-700", 700, labels=("focus",))
    open_blocker = node("H-201", 201, blocking=(ref("H-202"),))
    hidden_dependent = node("H-202", 202, labels=("focus",),
                            blocked_by=(ref("H-201"),))
    cross = node("X-12", 12, body="Text says #blocks 13, but that is not a native edge.",
                 blocked_by=(ref("EXT-81", "other/private"),))
    incomplete = node("I-3", 3, labels=("focus",), label_count=2,
                      blocked_by=(None, ref("EXT-3", "other/private")), blocker_count=3)
    cycle_a = node("C-21", 21, blocked_by=(ref("C-22"),), blocking=(ref("C-22"),))
    cycle_b = node("C-22", 22, blocked_by=(ref("C-21"),), blocking=(ref("C-21"),))
    self_loop = node("C-23", 23, blocked_by=(ref("C-23"),))
    downstream = node("C-24", 24, blocked_by=(ref("C-22"),))
    return {
        "paged_closed_blocker": [page([closed], 3, more=True, cursor="next-1"),
                                 page([dependent, isolated], 3)],
        "hidden_open_blocker": [page([open_blocker, hidden_dependent], 2)],
        "cross_repo_text": [page([cross], 1)],
        "incomplete_connections": [page([incomplete, None], 2)],
        "interrupted_page": [page([node("T-4", 4)], 2, more=True, cursor="next-2"),
                             {"errors": [{"message": "synthetic interruption"}]}],
        "unavailable_repository": [{"data": {"repository": None}}],
        "cycles": [page([cycle_a, cycle_b, self_loop, downstream,
                         node("C-25", 25)], 5)],
        "refresh_before": [page([node("R-123", 123)], 1)],
        "refresh_after": [page([{**node("R-123", 123, "CLOSED"),
                                 "updatedAt": "2026-10-05T10:00:00Z"}], 1)],
    }
