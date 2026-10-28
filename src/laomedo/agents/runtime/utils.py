"""Run workspace, native evidence and container preparation helpers."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID
from uuid import uuid4
import hashlib
import json
import laomedo.agents.runtime.settings as _runtime_settings
import laomedo.agents.runtime.errors as _runtime_errors
import laomedo.host.credentials.siwc.errors as _siwc_errors
import laomedo.host.leases.settings as _leases_settings
import os
import shutil
import stat
import subprocess
import time


def _git_tree(path: Path) -> bool:
    return any((parent / ".git").exists() for parent in (path, *path.parents))


def _private(path: Path) -> Path:
    path = path.expanduser().resolve()
    if _git_tree(path) or path.is_symlink():
        raise _runtime_errors.RunnerError("private_state_must_be_outside_git")
    return path


def _json(path: Path, value: dict) -> None:
    pending = path.with_name(path.name + ".pending-" + uuid4().hex)
    pending.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    try:
        # Windows can deny replacement while a concurrent poll has the old
        # record open. Keep the write atomic; only retry that transient lock.
        for attempt in range(20):
            try:
                os.replace(pending, path)
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.01)
    finally:
        pending.unlink(missing_ok=True)


def _read(path: Path) -> dict:
    # A concurrent atomic replacement can briefly deny a Windows reader.
    for attempt in range(5):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            break
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.01)
    if not isinstance(value, dict):
        raise _runtime_errors.RunnerError("invalid_record")
    return value


def _hash_tree(path: Path, *, exclude_root_git: bool = False) -> str:
    """Hash regular files and directories, including empty directories."""
    if not path.is_dir() or path.is_symlink():
        raise _runtime_errors.RunnerError("invalid_workspace")
    files = {}
    directories = []
    total_bytes = 0
    for parent, dirs, names in os.walk(path, followlinks=False):
        if exclude_root_git and Path(parent) == path:
            dirs[:] = [name for name in dirs if name != ".git"]
            names = [name for name in names if name != ".git"]
        for name in dirs + names:
            item = Path(parent) / name
            if (
                item.is_symlink()
                or getattr(item.lstat(), "st_file_attributes", 0)
                & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
                or not (item.is_dir() or item.is_file())
            ):
                raise _runtime_errors.RunnerError("unsafe_workspace_entry")
            if item.is_file():
                if item.stat().st_nlink != 1:
                    raise _runtime_errors.RunnerError("unsafe_workspace_entry")
                if exclude_root_git:
                    total_bytes += item.stat().st_size
                    if (
                        total_bytes
                        > _runtime_settings.MAX_GIT_WORKSPACE_SNAPSHOT_BYTES
                        or len(files) + len(directories)
                        >= _runtime_settings.MAX_GIT_WORKSPACE_SNAPSHOT_ENTRIES
                    ):
                        raise _runtime_errors.RunnerError(
                            "git_workspace_snapshot_limit"
                        )
                files[item.relative_to(path).as_posix()] = item.read_bytes()
            else:
                directories.append(item.relative_to(path).as_posix())
                if (
                    exclude_root_git
                    and len(files) + len(directories)
                    > _runtime_settings.MAX_GIT_WORKSPACE_SNAPSHOT_ENTRIES
                ):
                    raise _runtime_errors.RunnerError("git_workspace_snapshot_limit")
    digest = hashlib.sha256()
    for relative in sorted(directories):
        encoded = relative.encode("utf-8")
        digest.update(b"D")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    for relative, data in sorted(files.items()):
        encoded = relative.encode("utf-8")
        digest.update(b"F")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return "sha256:" + digest.hexdigest()


def _copy_tree(source: Path, target: Path, *, exclude_root_git: bool = False) -> str:
    expected = _hash_tree(source, exclude_root_git=exclude_root_git)
    ignore = (
        (
            lambda parent, names: {
                name for name in names if Path(parent) == source and name == ".git"
            }
        )
        if exclude_root_git
        else None
    )
    shutil.copytree(source, target, ignore=ignore)
    if _hash_tree(target) != expected:
        raise _runtime_errors.RunnerError("workspace_copy_mismatch")
    return expected


def _id(value: str) -> str:
    if str(UUID(value)) != value:
        raise _runtime_errors.RunnerError("invalid_run_id")
    return value


def _native_error_summary(events: list[dict], turn_id: str) -> dict:
    """Project app-server error events to a closed, nontextual diagnostic schema."""
    counts = {}
    statuses = set()
    retry_events = 0
    error_events = 0
    last_kind = None
    for event in events:
        if event.get("method") != "error":
            continue
        params = event.get("params")
        if not isinstance(params, dict) or params.get("turnId") != turn_id:
            continue
        error_events += 1
        retry_events += params.get("willRetry") is True
        error = params.get("error")
        info = error.get("codexErrorInfo") if isinstance(error, dict) else None
        kind = "unknown"
        if isinstance(info, str) and info in _runtime_settings.NATIVE_ERROR_KINDS:
            kind = info
        elif isinstance(info, dict) and len(info) == 1:
            candidate, details = next(iter(info.items()))
            if candidate in _runtime_settings.NATIVE_ERROR_KINDS and isinstance(
                details, dict
            ):
                kind = candidate
                if candidate in _runtime_settings.NATIVE_HTTP_ERROR_KINDS:
                    status = details.get("httpStatusCode")
                    if type(status) is int and 100 <= status <= 599:
                        statuses.add(status)
        counts[kind] = counts.get(kind, 0) + 1
        last_kind = kind
    return {
        "schema_version": 1,
        "error_events": error_events,
        "retry_events": retry_events,
        "categories": counts,
        "http_status_codes": sorted(statuses),
        "last_category": last_kind,
    }


def _auth_record_error(exc: _siwc_errors.AuthError) -> tuple[str, str]:
    code = str(exc)
    if code == "auth_account_missing":
        return "auth_missing", "missing"
    if code == "auth_consent_denied":
        return "auth_consent_missing", "consent_denied"
    if code == "auth_scope_missing":
        return "auth_scope_denied", "scope_missing"
    if code in {
        "auth_refresh_unknown",
        "auth_refresh_lock_unavailable",
        "auth_refresh_response_invalid",
    }:
        return "auth_refresh_failed", code.removeprefix("auth_")
    if code == "auth_revoked":
        return "auth_revoked", "revoked"
    if code == "auth_account_mismatch":
        return "auth_account_mismatch", "account_mismatch"
    if code == "auth_generation_changed":
        return "auth_generation_changed", "generation_changed"
    return "auth_mode_unavailable", code.removeprefix("auth_")


def _docker_prefix(
    workspace: Path,
    canonical: Path,
    store_mount: Path,
    *,
    image: str = _runtime_settings.IMAGE,
    name: str | None = None,
    run_id: str | None = None,
    launch_token: str | None = None,
    capability: Path | None = None,
    mediator_url: str | None = None,
    mediator_instance: str | None = None,
    command_directory: Path | None = None,
    repository: str | None = None,
    branch: str | None = None,
    base_branch: str = "main",
    nested_sandbox: bool = True,
) -> list[str]:
    """The #146 Docker grant and mounts, with only per-run paths substituted."""
    name = name or "laomedo-codex-" + uuid4().hex
    seccomp = []
    if nested_sandbox:
        if (
            hashlib.sha256(_runtime_settings.SECCOMP.read_bytes()).hexdigest()
            != _runtime_settings.SECCOMP_SHA256
        ):
            raise _runtime_errors.RunnerError("seccomp_profile_changed")
        seccomp = ["--security-opt", "seccomp=" + str(_runtime_settings.SECCOMP)]
    labels = (
        [
            "--label",
            f"{_leases_settings.LABEL_RUN}={run_id}",
            "--label",
            f"{_leases_settings.LABEL_TOKEN}={launch_token}",
        ]
        if run_id and launch_token
        else []
    )
    mediation = (
        [
            "--mount",
            f"type=bind,source={capability},target=/run/laomedo/capability,readonly",
            "--mount",
            f"type=bind,source={_runtime_settings.MEDIATION_CLIENT},target=/run/laomedo/mediate.mjs,readonly",
            "--env",
            "LAOMEDO_MEDIATOR_URL=" + mediator_url,
            "--env",
            "LAOMEDO_MEDIATOR_INSTANCE=" + mediator_instance,
            "--env",
            "LAOMEDO_CAPABILITY_FILE=/run/laomedo/capability",
        ]
        if all(
            value is not None for value in (capability, mediator_url, mediator_instance)
        )
        else []
    )
    if (
        any(
            value is not None for value in (capability, mediator_url, mediator_instance)
        )
        and not mediation
    ):
        raise _runtime_errors.RunnerError("incomplete_mediator_mount")
    if command_directory is not None:
        if not mediation or repository is None or branch is None:
            raise _runtime_errors.RunnerError("incomplete_command_mount")
        mediation += [
            "--mount",
            f"type=bind,source={command_directory},target=/run/laomedo/bin,readonly",
            "--mount",
            f"type=bind,source={_runtime_settings.MEDIATION_CLIENT.with_name('agent_gh_adapter.mjs')},target=/run/laomedo/gh.mjs,readonly",
            "--mount",
            f"type=bind,source={_runtime_settings.MEDIATION_CLIENT.with_name('agent_git_remote.mjs')},target=/run/laomedo/git-remote.mjs,readonly",
            "--env",
            "LAOMEDO_REPOSITORY=" + repository,
            "--env",
            "LAOMEDO_RUN_BRANCH=" + branch,
            "--env",
            "LAOMEDO_BASE_BRANCH=" + base_branch,
            "--env",
            "PATH=/run/laomedo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        ]
    # Windows bind mounts need not be owned by the container's non-root UID.
    # Trust only our fixed workspace, never arbitrary paths or a wildcard.
    git_config = (
        [
            "--env",
            "GIT_CONFIG_COUNT=1",
            "--env",
            "GIT_CONFIG_KEY_0=safe.directory",
            "--env",
            "GIT_CONFIG_VALUE_0=/draft",
        ]
        if image in {_runtime_settings.GIT_IMAGE, _runtime_settings.GIT_IMAGE_ID}
        else []
    )
    return [
        "run",
        "--rm",
        "-i",
        "--name",
        name,
        *labels,
        "--pull=never",
        "--network",
        "bridge",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        *seccomp,
        "--pids-limit",
        "128",
        "--memory",
        "1g",
        "--user",
        "10001:10001",
        "--mount",
        f"type=volume,source={_runtime_settings.VOLUME},target=/home/runner/.codex",
        "--mount",
        f"type=bind,source={workspace},target=/draft",
        "--mount",
        f"type=bind,source={canonical},target=/canonical,readonly",
        "--mount",
        f"type=bind,source={store_mount},target=/store",
        "--mount",
        f"type=bind,source={_runtime_settings.CONFIG},target=/config.toml,readonly",
        *mediation,
        *git_config,
        "--workdir",
        "/draft",
        image,
        "sh",
        "-c",
        'cp /config.toml /home/runner/.codex/config.toml && exec codex "$@"',
        "bootstrap",
        "app-server",
        "--stdio",
    ]


def _docker_checked(*args: str, timeout: float = 15) -> str:
    try:
        result = subprocess.run(
            ["docker", *args], capture_output=True, text=True, timeout=timeout
        )
    except (OSError, subprocess.TimeoutExpired):
        raise _runtime_errors.RunnerError("docker_control_unavailable") from None
    if result.returncode:
        raise _runtime_errors.RunnerError("docker_control_failed")
    return result.stdout.strip()


def _split_profile(state: Path) -> str:
    return (
        "laomedo-codex-split-"
        + hashlib.sha256(str(state).encode("utf-8")).hexdigest()[:20]
    )


def _ensure_split_profile(name: str) -> None:
    found = subprocess.run(
        ["docker", "volume", "inspect", name], capture_output=True, timeout=10
    )
    if found.returncode == 0:
        return
    _docker_checked("volume", "create", name)
    try:
        _docker_checked(
            "run",
            "--rm",
            "--pull=never",
            "--network",
            "none",
            "--user",
            "0:0",
            "--cap-drop",
            "ALL",
            "--cap-add",
            "CHOWN",
            "--mount",
            f"type=volume,source={name},target=/home/runner/.codex",
            _runtime_settings.IMAGE,
            "chown",
            "10001:10001",
            "/home/runner/.codex",
            timeout=30,
        )
    except Exception:
        _docker_checked("volume", "rm", name)
        raise


def _command_summary(events: list[dict], turn_id: str) -> dict:
    """Project observed command lifetimes, never infer completion from shutdown."""
    commands = {}
    incomplete = False
    for index, event in enumerate(events):
        params = event.get("params") or {}
        if params.get("turnId") not in (None, turn_id):
            continue
        method = event.get("method")
        item = params.get("item") or {}
        if method == "item/commandExecution/outputDelta":
            identity = params.get("itemId")
        elif (
            method in {"item/started", "item/completed"}
            and item.get("type") == "commandExecution"
        ):
            identity = item.get("id")
        else:
            continue
        if not isinstance(identity, str) or not identity:
            incomplete = True
            continue
        command = commands.setdefault(
            identity,
            {
                "id": identity,
                "status": "unknown",
                "completion_observed": False,
                "exit_code": None,
                "event_indices": [],
                "output_event_indices": [],
            },
        )
        command["event_indices"].append(index)
        if method == "item/commandExecution/outputDelta" or item.get(
            "aggregatedOutput"
        ):
            command["output_event_indices"].append(index)
        if method == "item/completed" and item.get("status") != "inProgress":
            observed = item.get("status")
            if observed is None and type(item.get("exitCode")) is int:
                observed = "completed"
            terminal = {"completed", "failed", "declined", "cancelled", "interrupted"}
            terminal_observed = isinstance(observed, str) and observed in terminal
            command["completion_observed"] = terminal_observed
            command["status"] = observed if terminal_observed else "unknown"
            code = item.get("exitCode")
            command["exit_code"] = code if type(code) is int else None
        elif method == "item/started":
            # A later start with the same identity is ambiguous, not a new success.
            command["completion_observed"] = False
            command["status"] = "unknown"
            command["exit_code"] = None
    rows = list(commands.values())
    return {
        "commands": rows,
        "identity_incomplete": incomplete,
        "outstanding_ids": [
            row["id"] for row in rows if not row["completion_observed"]
        ],
    }


def _answer(events: list[dict]) -> str | None:
    answers = []
    for event in events:
        if event.get("method") != "item/completed":
            continue
        item = event.get("params", {}).get("item") or {}
        if item.get("type") == "agentMessage" and isinstance(item.get("text"), str):
            answers.append(item["text"])
    return answers[-1] if answers else None


def _execution_evidence(path, offset, record, turns, *, streams_closed, resumed=False):
    """Close this invocation's host-retained native trace, not task semantics.

    Missing identities, truncated logs, open tools and cleanup uncertainty never
    become complete merely because the agent returned an answer or exited zero.
    """
    incomplete = {"evidence_complete": "unknown", "completion_basis": None}

    def refuse(reason):
        return {**incomplete, "evidence_closure": {"version": 1, "reason": reason}}

    # The workspace is cumulative. Closing only this attempt cannot establish
    # evidence for earlier writes. Keep resumed publication closed until a
    # durable per-attempt history can prove every contributing attempt.
    if resumed:
        return refuse("resume_publication_evidence_unverified")
    if (
        not streams_closed
        or record.get("status") != "completed"
        or record.get("snapshot_ready") is not True
        or record.get("controller_cleanup") != "confirmed"
        or record.get("container_ownership", {}).get("cleanup_verified") is not True
    ):
        return refuse("execution_or_cleanup_unclosed")
    identities = [turn.get("turn_id") for turn in turns]
    if (
        not identities
        or any(not isinstance(value, str) or not value for value in identities)
        or len(set(identities)) != len(identities)
        or any(turn.get("status") != "completed" for turn in turns)
    ):
        return refuse("turn_identity_or_status_unclosed")
    try:
        with path.open("rb") as source:
            source.seek(offset)
            raw = source.read(64 * 1024 * 1024 + 1)
        if not raw or len(raw) > 64 * 1024 * 1024 or not raw.endswith(b"\n"):
            return refuse("trace_unclosed")
        events = [json.loads(line) for line in raw.splitlines()]
        if any(not isinstance(event, dict) for event in events):
            return refuse("trace_invalid")
    except (OSError, ValueError, UnicodeError):
        return refuse("trace_unreadable")
    completed, items, answer = set(), {}, None
    for event in events:
        method = event.get("method")
        if method == "invalid/json":
            return refuse("trace_invalid")
        params = event.get("params") or {}
        if not isinstance(params, dict):
            return refuse("trace_invalid")
        if method == "turn/completed":
            turn = params.get("turn") or {}
            if not isinstance(turn, dict):
                return refuse("trace_invalid")
            identity = turn.get("id")
            if identity in identities:
                if (
                    params.get("threadId") != record.get("thread_id")
                    or identity in completed
                    or turn.get("status") != "completed"
                ):
                    return refuse("native_terminal_unclosed")
                completed.add(identity)
        elif method in {"item/started", "item/completed"}:
            identity = params.get("turnId")
            if identity is None:
                return refuse("item_identity_unclosed")
            if identity not in identities:
                continue
            item = params.get("item") or {}
            if (
                params.get("threadId") != record.get("thread_id")
                or not isinstance(item, dict)
                or not isinstance(item.get("id"), str)
                or not item["id"]
                or not isinstance(item.get("type"), str)
                or identity in completed
            ):
                return refuse("item_identity_unclosed")
            key = (identity, item["id"])
            if method == "item/started":
                if key in items:
                    return refuse("item_identity_unclosed")
                items[key] = (item["type"], False)
            else:
                if key in items and (items[key][0] != item["type"] or items[key][1]):
                    return refuse("item_identity_unclosed")
                if item.get("status") == "inProgress":
                    return refuse("item_completion_unclosed")
                items[key] = (item["type"], True)
                if identity == identities[-1] and item["type"] == "agentMessage":
                    answer = item.get("text")
    if (
        completed != set(identities)
        or not items
        or any(not state[1] for state in items.values())
    ):
        return refuse("native_terminal_or_item_unclosed")
    for identity in identities:
        commands = _command_summary(events, identity)
        if commands["identity_incomplete"] or commands["outstanding_ids"]:
            return refuse("command_completion_unclosed")
    if not isinstance(answer, str) or not answer or answer != record.get("answer"):
        return refuse("retained_answer_mismatch")
    return {
        "evidence_complete": True,
        "completion_basis": "native_trace_closure",
        "evidence_closure": {
            "version": 1,
            "reason": "closed",
            "turn_count": len(identities),
            "item_count": len(items),
        },
    }


def _advertised_models(server):
    models, seen, ids, cursor = [], set(), set(), None
    for _ in range(50):
        response = server.request("model/list", {"cursor": cursor} if cursor else {})
        result = response.get("result")
        if not isinstance(result, dict) or not isinstance(result.get("data"), list):
            raise _runtime_errors.RunnerError("model_list_rejected")
        for item in result["data"]:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("id"), str)
                or not item["id"]
                or item["id"] in ids
            ):
                raise _runtime_errors.RunnerError("model_list_invalid_entry")
            efforts = item.get("supportedReasoningEfforts", [])
            if not isinstance(efforts, list):
                raise _runtime_errors.RunnerError("model_list_invalid_entry")
            efforts = [
                level.get("reasoningEffort") if isinstance(level, dict) else level
                for level in efforts
            ]
            if not all(isinstance(level, str) and level for level in efforts):
                raise _runtime_errors.RunnerError("model_list_invalid_entry")
            ids.add(item["id"])
            models.append({"id": item["id"], "efforts": efforts})
        cursor = result.get("nextCursor")
        if not cursor:
            return models
        if not isinstance(cursor, str) or cursor in seen:
            raise _runtime_errors.RunnerError("model_list_invalid_cursor")
        seen.add(cursor)
    raise _runtime_errors.RunnerError("model_list_page_limit")
