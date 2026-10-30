"""Opt-in local Claude access-credential mirror; host retains refresh ownership."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit
import json
from laomedo.agents.agents.claude.auth.errors import LocalClaudeLoginError
import math
import os
import re
import subprocess
import time


def mirror_login(
    profile, image, *, source=None, environment=None, minimum_validity_seconds=180
):
    # Only the trusted host calls this; browser/model payloads supply no paths.
    if not re.fullmatch(r"laomedo-claude-[a-z0-9-]+", profile) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}", image
    ):
        raise LocalClaudeLoginError("claude_local_login_copy_failed")
    if (
        type(minimum_validity_seconds) not in (int, float)
        or not math.isfinite(minimum_validity_seconds)
        or not 0 < minimum_validity_seconds <= 86400
    ):
        raise LocalClaudeLoginError("claude_local_login_copy_failed")
    allowed = {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "TEMP",
        "TMP",
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_CONFIG",
        "DOCKER_CERT_PATH",
        "DOCKER_TLS_VERIFY",
    }
    env = {
        k.upper(): v
        for k, v in (os.environ if environment is None else environment).items()
        if k.upper() in allowed
    }
    endpoint = None

    def docker(args, payload=None):
        try:
            result = subprocess.run(
                ["docker", *(["--host", endpoint] if endpoint else []), *args],
                input=payload,
                capture_output=True,
                env=env,
                timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            raise LocalClaudeLoginError("claude_local_login_copy_failed") from None
        if result.returncode:
            raise LocalClaudeLoginError("claude_local_login_copy_failed")
        return result.stdout

    try:
        endpoint = (
            json.loads(docker(["context", "inspect"]))[0]["Endpoints"]["docker"]["Host"]
            if env.get("DOCKER_CONTEXT") or not env.get("DOCKER_HOST")
            else env["DOCKER_HOST"]
        )
        url = urlsplit(endpoint)
        local_pipe = bool(
            re.fullmatch(
                r"npipe:/{2,4}\./pipe/[^/]+", endpoint.replace("\\", "/"), re.I
            )
        )
        if not (local_pipe or url.scheme == "unix" and not url.netloc):
            raise ValueError()
        env.pop("DOCKER_HOST", None)
        env.pop("DOCKER_CONTEXT", None)
        volume = json.loads(docker(["volume", "inspect", profile]))[0]
        if (volume.get("Labels") or {}).get("laomedo.provider") != "claude":
            raise ValueError()
    except (ValueError, KeyError, IndexError, TypeError):
        raise LocalClaudeLoginError("claude_local_login_copy_failed") from None
    try:
        value = json.loads(
            (source or Path.home() / ".claude/.credentials.json").read_text(
                encoding="utf-8"
            )
        )["claudeAiOauth"]
        access = value["accessToken"]
        expires = value["expiresAt"]
        if (
            not isinstance(access, str)
            or not access
            or len(access) > 32768
            or type(expires) not in (int, float)
            or not math.isfinite(expires)
        ):
            raise ValueError()
    except (OSError, ValueError, TypeError, KeyError):
        raise LocalClaudeLoginError("claude_host_login_unavailable") from None
    if expires <= (time.time() + minimum_validity_seconds + 30) * 1000:
        raise LocalClaudeLoginError("claude_host_login_expired")
    # Never duplicate the rotating refresh credential or host profile/session data.
    login = {
        key: value[key]
        for key in (
            "accessToken",
            "expiresAt",
            "scopes",
            "subscriptionType",
            "rateLimitTier",
        )
        if key in value
    }
    login["refreshToken"] = ""
    payload = json.dumps({"claudeAiOauth": login}).encode()
    script = """import os,sys,tempfile
p='/profile/config'
assert not os.path.islink(p)
os.makedirs(p,exist_ok=True)
existing=p+'/.credentials.json'
assert not os.path.islink(existing)
if os.path.exists(existing):
    import json
    with open(existing) as f: old=json.load(f)
    if old.get('claudeAiOauth',{}).get('refreshToken'):
        raise SystemExit('Dedicated profile has its own refresh-capable login; mirror refused')
fd,tmp=tempfile.mkstemp(prefix='.login-',dir=p)
try:
    with os.fdopen(fd,'wb') as f: f.write(sys.stdin.buffer.read())
    os.chmod(tmp,0o600)
    os.replace(tmp,p+'/.credentials.json')
finally:
    if os.path.exists(tmp): os.unlink(tmp)
"""
    docker(
        [
            "run",
            "--rm",
            "--init",
            "--network=none",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--read-only",
            "--pids-limit=32",
            "--memory=256m",
            "--cpus=1",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=16m",
            "--mount",
            f"type=volume,source={profile},target=/profile",
            "-i",
            "--entrypoint",
            "python3",
            image,
            "-c",
            script,
        ],
        payload,
    )
