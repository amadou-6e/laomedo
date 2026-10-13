"""Backend-only issue client, with no graph credential inputs."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from urllib import request, error
from .skill_source_client import NoRedirect


def issue_request(action, **payload):
    base = os.environ.get("LAOMEDO_GITHUB_ISSUE_URL", "")
    url = urlsplit(base)
    if (url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost", "host.docker.internal"} or
            url.username or url.password or url.query or url.fragment or url.path not in {"", "/"} or
            action not in {"discover", "execute"}):
        raise ValueError("issue_service_not_configured")
    try:
        token = Path(os.environ.get("LAOMEDO_GITHUB_ISSUE_TOKEN_FILE", "/run/secrets/laomedo-runner-token")).read_text(encoding="utf-8").strip()
        if not 32 <= len(token) <= 512:
            raise ValueError()
        call = request.Request(base.rstrip("/") + "/v1/github-issues/" + action,
            data=json.dumps(payload, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + token})
        with request.build_opener(NoRedirect()).open(call, timeout=90) as response:
            data = response.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError()
        return json.loads(data)
    except error.HTTPError as exc:
        category = "github_issue_unavailable"
        try:
            parsed = json.loads(exc.read(1024))
            from .github_issue_contract import ERROR_CODES
            if parsed.get("error_category") in ERROR_CODES:
                category = parsed["error_category"]
        except Exception:
            pass
        raise ValueError(category) from None
    except Exception:
        raise ValueError("github_issue_unavailable") from None
