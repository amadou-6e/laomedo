"""Concern-owned provider double for internal controls, never live acceptance."""

import copy
import json
from urllib.parse import urlsplit
from urllib.parse import parse_qs

from test_github.response import JsonResponse
from test_github.test_pull_requests.utils import raw_pr


class FakeGitHub:
    def __init__(self):
        self.prs = {
            1: raw_pr(1, ["research", "backend"]),
            2: raw_pr(2, ["research"]),
            3: raw_pr(3, ["backend"], "closed"),
        }
        self.writes = []
        self.timeout_after_write = False
        self.reject_labels = False
        self.full_pages = False
        self.before_read = None

    def open(self, call, timeout=15):
        path = urlsplit(call.full_url).path
        query = parse_qs(urlsplit(call.full_url).query)
        method = call.get_method()
        if path.endswith("/labels") and method == "GET":
            value = [{"name": "backend"}, {"name": "research"}]
        elif path.endswith("/pulls"):
            if self.full_pages:
                page = int(query["page"][0])
                value = [
                    raw_pr(n, ["backend"]) for n in range(page * 100, page * 100 + 100)
                ]
            else:
                value = [
                    copy.deepcopy(v)
                    for v in self.prs.values()
                    if query.get("state", ["open"])[0] in {"all", v["state"]}
                ]
        else:
            number = int(
                path.split("/")[-2] if path.endswith("/labels") else path.split("/")[-1]
            )
            if self.before_read and method == "GET":
                self.before_read(self.prs[number])
            value = copy.deepcopy(self.prs[number])
            if method in {"PATCH", "PUT"}:
                if method == "PUT" and self.reject_labels:
                    from urllib.error import HTTPError

                    raise HTTPError(call.full_url, 422, "dummy-secret", {}, None)
                changes = json.loads(call.data)
                self.writes.append((method, path, changes))
                for key, item in changes.items():
                    value[key] = (
                        [{"name": x} for x in item] if key == "labels" else item
                    )
                value["updated_at"] = "2026-10-13T00:01:00Z"
                self.prs[number] = copy.deepcopy(value)
                if self.timeout_after_write:
                    raise TimeoutError("dummy-secret")
                if method == "PUT":
                    value = value["labels"]

        return JsonResponse(value)
