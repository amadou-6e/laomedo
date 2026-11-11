from pathlib import Path
from laomedo.github.issues.gateway import GitHubIssueGateway
from laomedo.github.transport.rest import GitHubRestTransport
from laomedo.host.mediation.store import MediationStore

from test_github.test_issues.models import IssueCase


def raw_issue(number, labels, state="open"):
    return {
        "number": number,
        "repository_url": "https://api.github.com/repos/owner/repo",
        "html_url": f"https://github.com/owner/repo/issues/{number}",
        "node_id": "I_" + str(number),
        "title": "Task " + str(number),
        "body": "Current issue body",
        "state": state,
        "updated_at": "2026-10-13T00:00:00Z",
        "labels": [{"name": label} for label in labels],
    }


def create_case(directory):
    """Return fresh state; the caller owns its temporary directory lifetime."""
    from test_github.test_issues.provider import FakeGitHub

    clock = [100.0]
    store = MediationStore(Path(directory) / "mediation.sqlite", now=lambda: clock[0])
    provider = FakeGitHub()
    transport = GitHubRestTransport(
        "owner/repo", lambda: "DUMMY-PROVIDER-SECRET", opener=provider
    )
    grant_id, token = store.issue(
        run_id="run",
        invocation_id="invocation",
        repository="owner/repo",
        operations={"issue_update"},
        target_issues={1},
        ttl_seconds=60,
    )
    binding = {"token": token, "run_id": "run", "repository": "owner/repo"}
    gateway = GitHubIssueGateway(
        {"owner/repo": transport},
        store,
        lambda ref: case.binding if ref == "grant" else None,
    )
    url = "https://github.com/owner/repo"

    # These factory-owned objects must retain identity with gateway closures.
    case = IssueCase.model_construct(
        clock=clock,
        store=store,
        provider=provider,
        transport=transport,
        binding=binding,
        gateway=gateway,
        url=url,
        grant_id=grant_id,
    )

    return case
