"""Concern-owned provider double for internal controls, never live acceptance."""

import copy
import json
from urllib.parse import urlsplit
from urllib.parse import parse_qs

from test_github.response import JsonResponse
from test_github.test_issues.utils import raw_issue


class FakeGitHub:
    def __init__(self):
        self.issues = {
            1: raw_issue(1, ["research", "backend"]),
            2: raw_issue(2, ["research"]),
            3: raw_issue(3, ["backend"]),
            4: {**raw_issue(4, ["research", "backend"]), "pull_request": {}},
        }
        self.patch_count = 0
        self.timeout_after_write = False
        self.full_pages = False
        self.reject_patch = False

    def open(self, call, timeout=15):
        path = urlsplit(call.full_url).path
        query = parse_qs(urlsplit(call.full_url).query)
        method = call.get_method()
        if path.endswith("/labels"):
            value = [{"name": "backend"}, {"name": "research"}]
        elif path.endswith("/issues"):
            if self.full_pages:
                page = int(query["page"][0])
                value = [
                    raw_issue(n, ["backend"])
                    for n in range(page * 100, page * 100 + 100)
                ]
            else:
                value = [
                    copy.deepcopy(v)
                    for v in self.issues.values()
                    if query.get("state", ["open"])[0] in {"all", v["state"]}
                ]
        else:
            number = int(path.rsplit("/", 1)[1])
            value = copy.deepcopy(self.issues[number])
            if method == "PATCH":
                self.patch_count += 1
                if self.reject_patch:
                    from urllib.error import HTTPError

                    raise HTTPError(
                        call.full_url, 422, "dummy-provider-secret", {}, None
                    )
                changes = json.loads(call.data)
                for key, item in changes.items():
                    value[key] = (
                        [{"name": x} for x in item] if key == "labels" else item
                    )
                value["updated_at"] = "2026-10-13T00:01:00Z"
                self.issues[number] = copy.deepcopy(value)
                if self.timeout_after_write:
                    raise TimeoutError("dummy-provider-secret https://private.invalid")

        return JsonResponse(value)
