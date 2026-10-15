"""Backend-only pr client, with no graph credential inputs."""
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit
from urllib import request, error
from .skill_source_client import NoRedirect
from .github_pr_contract import ERROR_CODES, PRE_DISPATCH_ERRORS


def pr_request(action, **payload):
    base = os.environ.get("LAOMEDO_GITHUB_PR_URL", "")
    url = urlsplit(base)
    if (url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost", "host.docker.internal"} or
            url.username or url.password or url.query or url.fragment or url.path not in {"", "/"} or
            action not in {"discover", "execute", "prepare-feedback", "apply-feedback"}):
        raise ValueError("pr_service_not_configured")
    try:
        token = Path(os.environ.get("LAOMEDO_GITHUB_PR_TOKEN_FILE", "/run/secrets/laomedo-runner-token")).read_text(encoding="utf-8").strip()
        if not 32 <= len(token) <= 512:
            raise ValueError()
        call = request.Request(base.rstrip("/") + "/v1/github-prs/" + action,
            data=json.dumps(payload, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + token})
        with request.build_opener(NoRedirect()).open(call, timeout=90) as response:
            data = response.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError()
        result = json.loads(data)
        if not isinstance(result, dict):
            raise ValueError()
        if action == 'prepare-feedback' and (result.get('schema_version') != 'laomedo.pr-feedback-ticket.v1' or
                not isinstance(result.get('ticket'),str) or not re.fullmatch(r'[0-9a-f]{64}',result['ticket'])):
            raise ValueError()
        if action in {"execute", "apply-feedback"} and (result.get("schema_version") != "laomedo.github-pr.v1" or
                not isinstance(result.get("operation"), dict) or
                result["operation"].get("status") not in {"not_requested", "succeeded", "failed", "unknown"} or
                "pr" not in result or result["pr"] is not None and not isinstance(result["pr"], dict)):
            raise ValueError()
        return result
    except error.HTTPError as exc:
        category = "github_pr_unavailable"
        try:
            parsed = json.loads(exc.read(1024))
            if parsed.get("error_category") in ERROR_CODES:
                category = parsed["error_category"]
        except Exception:
            pass
        if action in {"execute", "apply-feedback"} and payload.get("operation") and (exc.code not in {400, 401} or category not in PRE_DISPATCH_ERRORS):
            category = "pr_write_unknown"
        raise ValueError(category) from None
    except Exception:
        raise ValueError("pr_write_unknown" if action in {"execute", "apply-feedback"} and payload.get("operation") else "github_pr_unavailable") from None
