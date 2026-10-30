from __future__ import annotations

import json
from pathlib import Path
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from laomedo.http.redirect import NoRedirect
from laomedo.skills.interface.sources.settings import Settings


def source_request(action, **body):
    settings = Settings()

    url = settings.url
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
        path = Path(settings.token_file)
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
        with urllib.request.build_opener(NoRedirect()).open(
            request, timeout=65
        ) as response:
            data = response.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError()
        return json.loads(data)
    except urllib.error.HTTPError as error:
        category = "source_discovery_failed"
        try:
            # One explicitly admitted uncertainty category; never forward remote text.
            data = error.read(16 * 1024 + 1)
            if len(data) <= 16 * 1024:
                payload = json.loads(data)
                if (
                    isinstance(payload, dict)
                    and payload.get("error_category") == "repository_cleanup_unverified"
                ):
                    category = "repository_cleanup_unverified"
        except Exception:
            pass
        finally:
            try:
                error.close()
            except Exception:
                category = "source_discovery_failed"
        raise ValueError(category) from None
    except Exception:
        raise ValueError("source_service_unavailable") from None
