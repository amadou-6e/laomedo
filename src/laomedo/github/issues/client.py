"""Backend-only issue client, with no graph credential inputs."""

from pathlib import Path
from urllib import error
from urllib import request
from urllib.parse import urlsplit
import json
import laomedo.github.issues.contract as _issues_contract
import laomedo.skills.sources.transport as _sources_transport
import laomedo.github.issues.settings as _issues_settings


def issue_request(action, **payload):
    settings = _issues_settings.Settings()
    base = settings.url
    url = urlsplit(base)
    if (
        url.scheme != "http"
        or url.hostname not in {"127.0.0.1", "localhost", "host.docker.internal"}
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
        or action not in {"discover", "execute"}
    ):
        raise ValueError("issue_service_not_configured")
    try:
        token = (
            Path(
                settings.token_file
            )
            .read_text(encoding="utf-8")
            .strip()
        )
        if not 32 <= len(token) <= 512:
            raise ValueError()
        call = request.Request(
            base.rstrip("/") + "/v1/github-issues/" + action,
            data=json.dumps(payload, ensure_ascii=False).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + token,
            },
        )
        with request.build_opener(_sources_transport.NoRedirect()).open(
            call, timeout=90
        ) as response:
            data = response.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError()
        result = json.loads(data)
        if not isinstance(result, dict):
            raise ValueError()
        if action == "execute" and (
            result.get("schema_version") != "laomedo.github-issue.v1"
            or not isinstance(result.get("operation"), dict)
            or result["operation"].get("status")
            not in {"not_requested", "succeeded", "failed", "unknown"}
            or "issue" not in result
            or result["issue"] is not None
            and not isinstance(result["issue"], dict)
        ):
            raise ValueError()
        return result
    except error.HTTPError as exc:
        category = "github_issue_unavailable"
        try:
            parsed = json.loads(exc.read(1024))
            if parsed.get("error_category") in _issues_contract.ERROR_CODES:
                category = parsed["error_category"]
        except Exception:
            pass
        if (
            action == "execute"
            and payload.get("operation")
            and (
                exc.code not in {400, 401}
                or category not in _issues_contract.PRE_DISPATCH_ERRORS
            )
        ):
            category = "issue_write_unknown"
        raise ValueError(category) from None
    except Exception:
        raise ValueError(
            "issue_write_unknown"
            if action == "execute" and payload.get("operation")
            else "github_issue_unavailable"
        ) from None
