"""Backend-only Skill operation credentials, never graph inputs."""

from laomedo.host.http import NoRedirect
from laomedo.skills.interface.operations.settings import Settings

from pathlib import Path
from urllib import request
from urllib.error import HTTPError
from laomedo.skills.operations.settings import MANUAL_ERROR_CODES
from urllib.parse import urlsplit
import json


def skill_request(action, **body):
    """Send a configured loopback Skill operation request and preserve conservative client outcomes."""
    settings = Settings()
    base = settings.url.rstrip("/")
    parsed = urlsplit(base)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "host.docker.internal"}
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
        or action
        not in {
            "prepare",
            "apply",
            "history",
            "diff",
            "compare",
            "editor",
            "save",
            "publish",
        }
    ):
        raise ValueError("skill_operation_service_not_configured")
    try:
        token = Path(settings.token_file).read_text().strip()
        if not 32 <= len(token) <= 512:
            raise ValueError()
        call = request.Request(
            base + "/v1/skill-operations/" + action,
            data=json.dumps(body).encode(),
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
            },
        )
        with request.build_opener(NoRedirect()).open(call, timeout=65) as response:
            raw = response.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            raise ValueError()
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except HTTPError as exc:
        if action in {"editor", "save", "publish"}:
            try:
                raw = exc.read(1024)
                code = json.loads(raw).get("error_category")
            except Exception:
                code = None
            raise ValueError(
                code if code in MANUAL_ERROR_CODES else "skill_manual_unavailable"
            ) from None
        raise ValueError("skill_operation_unavailable") from None
    except Exception:
        if action in {"editor", "save", "publish"}:
            raise ValueError("skill_manual_unavailable") from None
        raise ValueError("skill_operation_unavailable") from None
