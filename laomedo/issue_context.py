"""Read-only selected-issue context for the EXP-02 integration probe.

Timeline cross-references are candidates, not an exhaustive PR search and never
authorization to update a PR. All GitHub calls are reads through the existing
``gh`` login; no credentials or raw command errors enter the returned record.
"""

from datetime import datetime, timezone
import json
import re
import subprocess
from typing import Callable

from .work_graph.github import validate_repository


class IssueContextError(ValueError):
    """A typed failure that must not become an empty issue or PR list."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _gh_json(path: str) -> object:
    try:
        result = subprocess.run(
            ["gh", "api", path], capture_output=True, text=True,
            encoding="utf-8", timeout=60, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise IssueContextError("github_unavailable") from error
    if result.returncode:
        # GitHub deliberately conflates inaccessible and nonexistent resources.
        code = "github_unavailable"
        for status, category in ((301, "issue_moved"), (401, "github_unauthorized"),
                                 (403, "github_forbidden"), (404, "issue_unavailable"),
                                 (410, "issue_gone")):
            if re.search(rf"HTTP {status}\b", result.stderr):
                code = category
                break
        raise IssueContextError(code)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise IssueContextError("invalid_github_response") from error


def _issue(payload: object, repository: str, number: int) -> dict:
    if not isinstance(payload, dict):
        raise IssueContextError("invalid_issue_response")
    expected = f"https://api.github.com/repos/{repository}"
    if payload.get("repository_url", "").lower() != expected.lower():
        raise IssueContextError("issue_moved_or_mismatched")
    if payload.get("number") != number or "pull_request" in payload:
        raise IssueContextError("not_selected_issue")
    if not payload.get("node_id") or not payload.get("updated_at"):
        raise IssueContextError("incomplete_issue_identity")
    return {
        "repository": repository,
        "number": number,
        "node_id": payload["node_id"],
        "url": payload["html_url"],
        "title": payload["title"],
        "body": payload.get("body") or "",
        "state": payload["state"],
        "updated_at": payload["updated_at"],
    }


def _pr_candidates(events: list[dict]) -> list[dict]:
    candidates: dict[tuple[str, int], dict] = {}
    for event in events:
        if event.get("event") != "cross-referenced":
            continue
        source = (event.get("source") or {}).get("issue") or {}
        if "pull_request" not in source or source.get("state") != "open":
            continue
        repository = ((source.get("repository") or {}).get("full_name") or "")
        if not repository:
            prefix = "https://api.github.com/repos/"
            repository_url = source.get("repository_url") or ""
            if repository_url.startswith(prefix):
                repository = repository_url[len(prefix):]
        number, url = source.get("number"), source.get("html_url")
        if not repository or not isinstance(number, int) or not url or not source.get("node_id"):
            raise IssueContextError("incomplete_pr_reference")
        candidates[(repository.lower(), number)] = {
            "repository": repository, "number": number,
            "node_id": source["node_id"], "url": url,
            "evidence": "timeline_cross_reference",
        }
    return [candidates[key] for key in sorted(candidates)]


def fetch_context(
    repository: str, number: int, *, supplied_target_pr: int | None = None,
    request: Callable[[str], object] = _gh_json, fetched_at: str | None = None,
    max_timeline_pages: int = 20,
) -> dict:
    """Fetch current issue text and discover open timeline-cross-referenced PRs.

    A missing timeline never becomes a confirmed empty candidate list. A changed
    issue during this non-atomic read is rejected rather than called a snapshot.
    """
    validate_repository(repository)
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise ValueError("Issue number must be positive")
    if supplied_target_pr is not None and (
        not isinstance(supplied_target_pr, int) or isinstance(supplied_target_pr, bool)
        or supplied_target_pr < 1
    ):
        raise ValueError("Supplied PR number must be positive")
    if max_timeline_pages < 1:
        raise ValueError("Timeline page limit must be positive")
    issue_path = f"repos/{repository}/issues/{number}"
    issue = _issue(request(issue_path), repository, number)
    events: list[dict] = []
    complete, warning = True, None
    for page in range(1, max_timeline_pages + 1):
        try:
            batch = request(f"{issue_path}/timeline?per_page=100&page={page}")
        except IssueContextError:
            complete, warning = False, "timeline_unavailable"
            break
        if not isinstance(batch, list) or any(not isinstance(item, dict) for item in batch):
            complete, warning = False, "invalid_timeline_response"
            break
        events.extend(batch)
        if len(batch) < 100:
            break
    else:
        complete, warning = False, "timeline_page_limit"
    # Current issue text and the PR timeline are not an atomic GitHub snapshot.
    confirmed = _issue(request(issue_path), repository, number)
    if confirmed != issue:
        raise IssueContextError("issue_changed_during_fetch")
    candidates = _pr_candidates(events)
    return {
        "issue": issue,
        "fetched_at": fetched_at or datetime.now(timezone.utc).isoformat(),
        "related_open_prs": candidates,
        "related_prs_complete": complete,
        "related_prs_warning": warning,
        "related_prs_scope": "timeline_cross_references_only",
        "supplied_target_pr": (
            {"repository": repository, "number": supplied_target_pr,
             "url": f"https://github.com/{repository}/pull/{supplied_target_pr}"}
            if supplied_target_pr is not None else None
        ),
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", help="owner/repo")
    parser.add_argument("issue", type=int)
    parser.add_argument("--target-pr", type=int, default=None)
    args = parser.parse_args()
    try:
        result = fetch_context(args.repository, args.issue, supplied_target_pr=args.target_pr)
    except IssueContextError as error:
        print(json.dumps({"error": error.code}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
