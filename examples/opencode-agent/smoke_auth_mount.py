"""Credential-free Docker smoke test for the nonpersistent auth file mount."""

import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from laomedo.opencode_boundary import IsolatedOpenCode
from laomedo.local_runner import _json
from acceptance import IMAGE, IMAGE_ID


def main():
    root = Path(os.environ["LOCALAPPDATA"]) / "Laomedo" / ("opencode-auth-mount-" + uuid4().hex)
    root.mkdir(parents=True)
    profile, evidence = root / "profile", root / "evidence"
    profile.mkdir()
    evidence.mkdir()
    workspace = root / "workspace"
    shutil.copytree(ROOT / "examples/skill-agent-pilot/source", workspace)
    shutil.copytree(workspace, evidence / "canonical")
    (evidence / "store").mkdir()
    (evidence / "store/sentinel.txt").write_text("STORE-ORIGINAL")
    skill = workspace / ".agents/skills/canary"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# Canary skill\n")
    key = "CANARY-" + secrets.token_hex(24)
    _json(profile / "auth.json", {"opencode-go": {"type": "api", "key": key}})
    _json(profile / "auth-validity.json", {"credential_mode": "provider_key",
         "expires_at_ms": None, "credential_sha256": hashlib.sha256(key.encode()).hexdigest()})
    backend = None
    try:
        backend = IsolatedOpenCode(workspace, evidence, profile=profile,
                                   image=IMAGE, image_id=IMAGE_ID)
        health = backend.call("GET", "/global/health")
        if not health.get("healthy"):
            raise RuntimeError("canary_controller_unhealthy")
        placeholder = profile / "sessions/auth.json"
        if placeholder.exists() and placeholder.stat().st_size != 0:
            raise RuntimeError("credential_bytes_persisted_in_session_mount")
    finally:
        if backend is not None:
            backend.close()
    placeholder = profile / "sessions/auth.json"
    result = {"controller_healthy": True, "session_auth_placeholder_empty":
              not placeholder.exists() or placeholder.stat().st_size == 0,
              "model_turns_submitted": 0}
    _json(root / "summary.json", result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
