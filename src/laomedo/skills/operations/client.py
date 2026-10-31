"""Backend-only Skill operation credentials, never graph inputs."""

from pathlib import Path
from urllib import request
from urllib.parse import urlsplit
import json
import laomedo.skills.sources.transport as _sources_transport
import laomedo.skills.operations.settings as _operations_settings


def skill_request(action, **body):
    settings = _operations_settings.Settings()
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
        or action not in {"prepare", "apply", "history", "diff", "compare"}
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
        with request.build_opener(_sources_transport.NoRedirect()).open(
            call, timeout=65
        ) as response:
            raw = response.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            raise ValueError()
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except Exception:
        raise ValueError("skill_operation_unavailable") from None
