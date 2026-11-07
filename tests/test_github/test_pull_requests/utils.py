from pathlib import Path
from laomedo.github.pull_requests.gateway import GitHubPRGateway
from laomedo.github.transport.rest.transport import GitHubRestTransport
from laomedo.host.mediation.store import MediationStore

from test_github.test_pull_requests.models import PullRequestCase


def raw_pr(number, labels, state="open"):
    return {
        "number": number,
        "html_url": f"https://github.com/owner/repo/pull/{number}",
        "node_id": f"PR_{number}",
        "title": f"Change {number}",
        "body": "Current PR body",
        "state": state,
        "draft": True,
        "merged_at": None,
        "updated_at": "2026-10-13T00:00:00Z",
        "labels": [{"name": x} for x in labels],
        "head": {"ref": "demo", "sha": "a" * 40, "repo": {"full_name": "owner/repo"}},
        "base": {"ref": "main", "repo": {"full_name": "owner/repo"}},
    }


def create_case(directory):
    """Return fresh state; the caller owns its temporary directory lifetime."""
    from test_github.test_pull_requests.provider import FakeGitHub

    clock = [100.0]
    store = MediationStore(Path(directory) / "mediation.db", now=lambda: clock[0])
    provider = FakeGitHub()
    transport = GitHubRestTransport(
        "owner/repo", lambda: "DUMMY-TOKEN", opener=provider
    )
    _, token = store.issue(
        run_id="run",
        invocation_id="invoke",
        repository="owner/repo",
        operations={"pr_node_update"},
        target_prs={1: "main"},
        branch="demo",
        ttl_seconds=60,
    )
    binding = {"token": token, "run_id": "run", "repository": "owner/repo"}
    gateway = GitHubPRGateway(
        {"owner/repo": transport},
        store,
        lambda ref: case.binding if ref == "grant" else None,
    )
    url = "https://github.com/owner/repo"

    # These factory-owned objects must retain identity with gateway closures.
    case = PullRequestCase.model_construct(
        clock=clock,
        store=store,
        provider=provider,
        transport=transport,
        binding=binding,
        gateway=gateway,
        url=url,
    )

    return case
