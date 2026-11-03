import copy

REPO = "example/work"


def issue(**changes):
    return {
        "repository_url": f"https://api.github.com/repos/{REPO}",
        "number": 7,
        "node_id": "I_7",
        "html_url": f"https://github.com/{REPO}/issues/7",
        "title": "Current title",
        "body": "Current body",
        "state": "open",
        "updated_at": "2026-10-02T12:00:00Z",
        **changes,
    }


def cross_reference(number=9, state="open", repository=REPO):
    return {
        "event": "cross-referenced",
        "source": {
            "issue": {
                "repository_url": f"https://api.github.com/repos/{repository}",
                "number": number,
                "node_id": f"PR_{number}",
                "html_url": f"https://github.com/{repository}/pull/{number}",
                "state": state,
                "pull_request": {"url": "api-ref"},
            }
        },
    }


def responder(first=None, timeline=None, second=None):
    responses = [
        first if first is not None else issue(),
        timeline if timeline is not None else [cross_reference()],
        second if second is not None else issue(),
    ]
    calls = []

    def request(path):
        calls.append(path)
        return copy.deepcopy(responses.pop(0))

    return request, calls
