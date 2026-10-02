"""EXP-02: selected issue and discovered PRs have distinct identities."""

import copy
import subprocess
import unittest
from unittest.mock import patch

from laomedo.issue_context import IssueContextError, _gh_json, fetch_context


REPO = "example/work"
BASE = f"repos/{REPO}/issues/7"


def issue(**changes):
    return {
        "repository_url": f"https://api.github.com/repos/{REPO}",
        "number": 7, "node_id": "I_7",
        "html_url": f"https://github.com/{REPO}/issues/7",
        "title": "Current title", "body": "Current body", "state": "open",
        "updated_at": "2026-10-02T12:00:00Z", **changes,
    }


def cross_reference(number=9, state="open", repository=REPO):
    return {
        "event": "cross-referenced",
        "source": {"issue": {
            "repository_url": f"https://api.github.com/repos/{repository}",
            "number": number, "node_id": f"PR_{number}",
            "html_url": f"https://github.com/{repository}/pull/{number}",
            "state": state, "pull_request": {"url": "api-ref"},
        }},
    }


def responder(first=None, timeline=None, second=None):
    responses = [first if first is not None else issue(),
                 timeline if timeline is not None else [cross_reference()],
                 second if second is not None else issue()]
    calls = []

    def request(path):
        calls.append(path)
        return copy.deepcopy(responses.pop(0))

    return request, calls


class IssueContextTests(unittest.TestCase):
    def test_transport_classifies_unavailable_without_leaking_stderr(self):
        for status, expected in ((301, "issue_moved"), (403, "github_forbidden"),
                                 (404, "issue_unavailable"), (410, "issue_gone")):
            response = subprocess.CompletedProcess([], 1, "", f"HTTP {status}: secret detail")
            with patch("laomedo.issue_context.subprocess.run", return_value=response):
                with self.assertRaises(IssueContextError) as caught:
                    _gh_json(BASE)
            self.assertEqual(caught.exception.code, expected)
            self.assertNotIn("secret", str(caught.exception))

    def test_discovered_pr_does_not_become_supplied_target(self):
        request, calls = responder(timeline=[cross_reference(), cross_reference(),
                                             cross_reference(10, "closed")])
        context = fetch_context(REPO, 7, request=request,
                                fetched_at="2026-10-02T12:01:00Z")
        self.assertEqual(context["issue"]["node_id"], "I_7")
        self.assertEqual(context["issue"]["body"], "Current body")
        self.assertEqual([pr["number"] for pr in context["related_open_prs"]], [9])
        self.assertIsNone(context["supplied_target_pr"])
        self.assertTrue(context["related_prs_complete"])
        self.assertEqual(calls, [BASE, BASE + "/timeline?per_page=100&page=1", BASE])

    def test_explicit_target_stays_distinct_even_when_not_discovered(self):
        request, _ = responder()
        context = fetch_context(REPO, 7, supplied_target_pr=12, request=request)
        self.assertEqual(context["related_open_prs"][0]["number"], 9)
        self.assertEqual(context["supplied_target_pr"]["number"], 12)

    def test_cross_repository_pr_and_second_timeline_page(self):
        first = [{"event": "commented"} for _ in range(100)]
        replies = [issue(), first, [cross_reference(3, repository="other/work")], issue()]
        calls = []

        def request(path):
            calls.append(path)
            return replies.pop(0)

        result = fetch_context(REPO, 7, request=request)
        self.assertEqual(result["related_open_prs"][0]["repository"], "other/work")
        self.assertEqual(calls[-2], BASE + "/timeline?per_page=100&page=2")

    def test_timeline_failure_is_not_a_confirmed_empty_result(self):
        replies = [issue(), IssueContextError("github_unavailable"), issue()]

        def request(_):
            value = replies.pop(0)
            if isinstance(value, Exception):
                raise value
            return value

        result = fetch_context(REPO, 7, request=request)
        self.assertEqual(result["related_open_prs"], [])
        self.assertFalse(result["related_prs_complete"])
        self.assertEqual(result["related_prs_warning"], "timeline_unavailable")

    def test_moved_inaccessible_and_changed_issues_fail_explicitly(self):
        request, _ = responder(first=issue(repository_url="https://api.github.com/repos/other/work"))
        with self.assertRaisesRegex(IssueContextError, "issue_moved_or_mismatched"):
            fetch_context(REPO, 7, request=request)
        request, _ = responder(second=issue(updated_at="2026-10-02T12:02:00Z"))
        with self.assertRaisesRegex(IssueContextError, "issue_changed_during_fetch"):
            fetch_context(REPO, 7, request=request)

        def unavailable(_):
            raise IssueContextError("issue_unavailable")

        with self.assertRaisesRegex(IssueContextError, "issue_unavailable"):
            fetch_context(REPO, 7, request=unavailable)

    def test_pr_is_not_an_issue_and_inputs_are_bounded(self):
        request, _ = responder(first=issue(pull_request={"url": "api-ref"}))
        with self.assertRaisesRegex(IssueContextError, "not_selected_issue"):
            fetch_context(REPO, 7, request=request)
        with self.assertRaises(ValueError):
            fetch_context("unsafe/../repo", 7)
        with self.assertRaises(ValueError):
            fetch_context(REPO, 0)
        with self.assertRaises(ValueError):
            fetch_context(REPO, 7, supplied_target_pr=-1)


if __name__ == "__main__":
    unittest.main()
