"""Backend-only client. Source credentials never become Langflow input fields."""
from pathlib import Path
from urllib.parse import urlsplit
import json
import os
import urllib.request
import urllib.error


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def source_request(action, **body):
    url = os.environ.get("LAOMEDO_SKILL_SOURCE_URL", "")
    parsed = urlsplit(url)
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "host.docker.internal"} or
            parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}):
        raise ValueError("source_service_not_configured")
    if action not in {"discover", "revisions", "resolve"}:
        raise ValueError("invalid_source_operation")
    try:
        path = Path(os.environ.get("LAOMEDO_SKILL_SOURCE_TOKEN_FILE", "/run/secrets/laomedo-runner-token"))
        token = path.read_text(encoding="utf-8").strip()
        if not 32 <= len(token) <= 512:
            raise ValueError()
        request = urllib.request.Request(url.rstrip("/") + "/v1/skill-sources/" + action,
            data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "Authorization": "Bearer " + token})
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=65) as response:
            data = response.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError()
        return json.loads(data)
    except urllib.error.HTTPError:
        raise ValueError("source_discovery_failed") from None
    except Exception:
        raise ValueError("source_service_unavailable") from None
