from __future__ import annotations
import urllib.request

from pathlib import Path
from pathlib import PurePosixPath
from urllib.parse import urlsplit
import json
import laomedo.skills.inspection.settings as _inspection_settings
import laomedo.skills.registry.settings as _registry_settings
import laomedo.skills.registry.errors as _registry_errors
import laomedo.skills.registry.utils as _registry_utils
import laomedo.skills.sources.settings as _sources_settings
import laomedo.skills.sources.errors as _sources_errors
import os
import re
import urllib.error


def source_request(action, **body):
    import laomedo.skills.sources.transport as _sources_transport

    url = os.environ.get("LAOMEDO_SKILL_SOURCE_URL", "")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "host.docker.internal"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("source_service_not_configured")
    if action not in {"discover", "revisions", "resolve"}:
        raise ValueError("invalid_source_operation")
    try:
        path = Path(
            os.environ.get(
                "LAOMEDO_SKILL_SOURCE_TOKEN_FILE", "/run/secrets/laomedo-runner-token"
            )
        )
        token = path.read_text(encoding="utf-8").strip()
        if not 32 <= len(token) <= 512:
            raise ValueError()
        request = urllib.request.Request(
            url.rstrip("/") + "/v1/skill-sources/" + action,
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + token,
            },
        )
        with urllib.request.build_opener(_sources_transport.NoRedirect()).open(
            request, timeout=65
        ) as response:
            data = response.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError()
        return json.loads(data)
    except urllib.error.HTTPError:
        raise ValueError("source_discovery_failed") from None
    except Exception:
        raise ValueError("source_service_unavailable") from None
