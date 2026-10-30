"""Opt-in local access-only mirror through py-docker's owned Session lifecycle."""

from importlib.resources import files
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlsplit
from uuid import uuid4

from laomedo.agents.agents.claude.auth.errors import LocalClaudeLoginError
from laomedo.agents.agents.claude.auth.models import ClaudeAccessLoginRecord
from laomedo.agents.agents.claude.auth.settings import (
    CLEANUP_SECONDS,
    COPY_SECONDS,
    Settings,
)
from laomedo.host.private_state.models import DirectoryPermissionPolicy
from laomedo.host.private_state.utils import prepare_private_directory
from laomedo.host.private_state.windows import WindowsDirectorySecurity


def _remaining(deadline: float, ceiling: float = 20.0) -> float:
    """Clamp one stage to its original normal-phase admission deadline."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise LocalClaudeLoginError("claude_local_login_copy_failed")
    return min(remaining, ceiling)


def _local_endpoint(environment: dict[str, str], deadline: float) -> str:
    """Preserve bare CLI context selection, then admit only a local socket."""
    if environment.get("DOCKER_CONTEXT") or not environment.get("DOCKER_HOST"):
        result = subprocess.run(
            ["docker", "context", "inspect"],
            capture_output=True,
            env=environment,
            timeout=_remaining(deadline),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode:
            raise LocalClaudeLoginError("claude_local_login_copy_failed")
        endpoint = json.loads(result.stdout)[0]["Endpoints"]["docker"]["Host"]
    else:
        endpoint = environment["DOCKER_HOST"]
    if not isinstance(endpoint, str):
        raise LocalClaudeLoginError("claude_local_login_copy_failed")
    # Do not normalize a CLI-rejected spelling into a different valid target.
    if re.fullmatch(r"npipe:////\./pipe/[^/\\]+", endpoint):
        return endpoint
    url = urlsplit(endpoint)
    if (
        url.scheme == "unix"
        and not url.netloc
        and url.path.startswith("/")
        and not url.query
        and not url.fragment
        and "\\" not in endpoint
    ):
        return "unix://" + url.path
    raise LocalClaudeLoginError("claude_local_login_copy_failed")


def _private_directory(
    snapshot: dict[str, str], settings: Settings, deadline: float
) -> Path:
    """Admit a host-owned leaf outside Git without changing existing leaf ACLs."""
    if settings.private_state_directory is not None:
        path = Path(settings.private_state_directory)
    elif os.name == "nt":
        base = snapshot.get("LOCALAPPDATA")
        if not base:
            raise LocalClaudeLoginError("claude_local_login_copy_failed")
        path = Path(base) / "Laomedo" / "state" / "claude-login"
    else:
        xdg = snapshot.get("XDG_STATE_HOME")
        base = (
            Path(xdg)
            if xdg and Path(xdg).is_absolute()
            else Path.home() / ".local/state"
        )
        path = base / "laomedo" / "claude-login"
    policy = None
    if os.name == "nt":
        system = WindowsDirectorySecurity().system_directory()
        policy = DirectoryPermissionPolicy(
            whoami=system / "whoami.exe",
            icacls=system / "icacls.exe",
            environment=snapshot,
            deadline=deadline,
        )
    prepare_private_directory(path, policy=policy)
    return path


def mirror_login(
    profile,
    image,
    *,
    source=None,
    environment=None,
    minimum_validity_seconds=180,
    deadline=None,
):
    """Copy only the selected access login; exact cleanup owns outcome precedence.

    The source is read only after endpoint, private-state and dedicated-volume
    admission. Credential bytes travel solely through session stdin. The host
    remains refresh owner. Explicit deadlines cap admission, not hard wall time.
    """
    if not re.fullmatch(r"laomedo-claude-[a-z0-9-]+", profile) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}", image
    ):
        raise LocalClaudeLoginError("claude_local_login_copy_failed")
    if (
        type(minimum_validity_seconds) not in (int, float)
        or not math.isfinite(minimum_validity_seconds)
        or not 0 < minimum_validity_seconds <= 86400
        or deadline is not None
        and (type(deadline) not in (int, float) or not math.isfinite(deadline))
    ):
        raise LocalClaudeLoginError("claude_local_login_copy_failed")
    normal_deadline = time.monotonic() + COPY_SECONDS
    if deadline is not None:
        normal_deadline = min(normal_deadline, deadline)
    snapshot = dict(os.environ if environment is None else environment)
    # Explicit None prevents supplied settings falling through to ambient values.
    settings = Settings(
        LAOMEDO_CLAUDE_MIRROR_HOST_LOGIN=snapshot.get(
            "LAOMEDO_CLAUDE_MIRROR_HOST_LOGIN"
        ),
        LAOMEDO_CLAUDE_LOGIN_STATE_DIR=snapshot.get("LAOMEDO_CLAUDE_LOGIN_STATE_DIR"),
    )
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
    docker_environment = {
        key.upper(): value for key, value in snapshot.items() if key.upper() in allowed
    }
    client = None
    failure = None
    try:
        from py_docker import Client
        from py_docker.connection.settings import ConnectionSettings
        from py_docker.containers.models import ContainerSpec, Mount
        from py_docker.sessions.models import ContainerSession
        from py_docker.streams.models import StreamLimits

        endpoint = _local_endpoint(docker_environment, normal_deadline)
        state = _private_directory(
            docker_environment | {"XDG_STATE_HOME": snapshot.get("XDG_STATE_HOME", "")},
            settings,
            normal_deadline,
        )
        for key in (
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
            "DOCKER_CERT_PATH",
            "DOCKER_TLS_VERIFY",
        ):
            docker_environment.pop(key, None)
        client = Client(
            ConnectionSettings(
                endpoint=endpoint,
                context=None,
                timeout_seconds=_remaining(normal_deadline),
            ),
            environment=docker_environment,
        )
        if not client.volumes.has_labels(profile, {"laomedo.provider": "claude"}):
            raise LocalClaudeLoginError("claude_local_login_copy_failed")
        _remaining(normal_deadline)
        try:
            value = json.loads(
                (source or Path.home() / ".claude/.credentials.json").read_text(
                    encoding="utf-8"
                )
            )["claudeAiOauth"]
            record = ClaudeAccessLoginRecord.from_host_record(value)
        except (OSError, ValueError, TypeError, KeyError):
            raise LocalClaudeLoginError("claude_host_login_unavailable") from None
        record.require_expiry_after(
            (time.time() + minimum_validity_seconds + 30) * 1000
        )
        payload = record.to_private_bytes()
        writer = (
            files("laomedo.agents.agents.claude.auth.resources")
            .joinpath("write_login.py")
            .read_text(encoding="utf-8")
        )
        request = ContainerSession(
            spec=ContainerSpec(
                image=image,
                name="laomedo-claude-login-" + uuid4().hex,
                entrypoint=["python3"],
                command=["-c", writer, str(len(payload))],
                mounts=[Mount(type="volume", source=profile, target="/profile")],
                init=True,
                stdin_open=True,
                log_driver="none",
                network_mode="none",
                read_only=True,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges"],
                pids_limit=32,
                mem_limit="256m",
                nano_cpus=1_000_000_000,
                tmpfs={"/tmp": "rw,nosuid,nodev,size=16m"},
            ),
            limits=StreamLimits(
                seconds=_remaining(normal_deadline, COPY_SECONDS), max_bytes=65536
            ),
            receipt_path=state / (profile + ".json"),
        )
        with client.sessions.open(
            request, deadline=float(normal_deadline), cleanup_seconds=CLEANUP_SECONDS
        ) as session:
            session.write(payload)
            while session.read_frame() is not None:
                pass  # Drain without logging or retaining private output.
            if session.wait(timeout=_remaining(normal_deadline)) != 0:
                raise LocalClaudeLoginError("claude_local_login_copy_failed")
    except LocalClaudeLoginError as error:
        failure = error
    except Exception:
        # SDK retains exact pending intent when cleanup cannot be confirmed.
        # Never dispatch a fallback CLI copy or another model request.
        failure = LocalClaudeLoginError("claude_local_login_copy_failed")
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                if failure is None:
                    failure = LocalClaudeLoginError("claude_local_login_copy_failed")
    if failure is not None:
        raise failure from None
