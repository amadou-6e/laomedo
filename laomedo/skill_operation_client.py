"""Backend-only Skill operation credentials, never graph inputs."""
import json
import os
from pathlib import Path
from urllib import request
from urllib.parse import urlsplit
from .skill_source_client import NoRedirect


def skill_request(action, **body):
    base = os.environ.get('LAOMEDO_SKILL_OPERATION_URL', '').rstrip('/')
    parsed = urlsplit(base)
    if (parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost', 'host.docker.internal'} or
            parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment or
            action not in {'prepare', 'apply', 'history', 'diff'}):
        raise ValueError('skill_operation_service_not_configured')
    try:
        token = Path(os.environ['LAOMEDO_SKILL_OPERATION_TOKEN_FILE']).read_text().strip()
        if not 32 <= len(token) <= 512:
            raise ValueError()
        call = request.Request(base+'/v1/skill-operations/'+action, data=json.dumps(body).encode(),
            headers={'Authorization': 'Bearer '+token, 'Content-Type': 'application/json'})
        with request.build_opener(NoRedirect()).open(call, timeout=65) as response:
            raw = response.read(16*1024*1024+1)
        if len(raw) > 16*1024*1024:
            raise ValueError()
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except Exception:
        raise ValueError('skill_operation_unavailable') from None
