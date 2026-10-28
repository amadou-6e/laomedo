"""Run workspace, native evidence and container preparation helpers."""

from __future__ import annotations
import laomedo.agents.providers.codex.settings as _codex_settings

from pathlib import Path
from uuid import uuid4
import hashlib
import json
import laomedo.agents.runtime.errors as _runtime_errors
import laomedo.host.credentials.siwc.errors as _siwc_errors



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
        if isinstance(info, str) and info in _codex_settings.NATIVE_ERROR_KINDS:
            kind = info
        elif isinstance(info, dict) and len(info) == 1:
            candidate, details = next(iter(info.items()))
            if candidate in _codex_settings.NATIVE_ERROR_KINDS and isinstance(
                details, dict
            ):
                kind = candidate
                if candidate in _codex_settings.NATIVE_HTTP_ERROR_KINDS:
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


def _split_profile(state: Path) -> str:
    return (
        "laomedo-codex-split-"
        + hashlib.sha256(str(state).encode("utf-8")).hexdigest()[:20]
    )


def _ensure_split_profile(name: str, *, state: Path, env=None) -> None:
    """Reuse the explicitly selected profile or initialize a newly owned volume.

    Failed initialization retains the volume rather than deleting a mutable name.
    The one-shot container keeps its own durable cleanup receipt in runner state.
    """
    from docker.errors import NotFound, DockerException
    from py_docker import Client
    from py_docker.containers.models import ContainerSpec, Mount
    from py_docker.jobs.models import ContainerJob
    from py_docker.streams.models import StreamLimits
    from py_docker.errors import CleanupUnconfirmedError
    try:
        with Client(environment=env) as client:
            client.jobs.recover(state.joinpath("profile-init.json"))
            try:
                client.sdk.volumes.get(name)  # Explicit host-selected existing profile.
            except NotFound:
                client.volumes.create(name=name)
            image=client.images.resolve(_codex_settings.IMAGE, expected_id=_codex_settings.IMAGE_ID)
            result=client.jobs.run(ContainerJob(
                spec=ContainerSpec(image=image,name="laomedo-profile-"+uuid4().hex,
                    user="0:0",cap_add=["CHOWN"],command=["chown","10001:10001","/home/runner/.codex"],
                    mounts=[Mount(type="volume",source=name,target="/home/runner/.codex")]),
                limits=StreamLimits(seconds=30,max_bytes=65536),wait_timeout_seconds=30,
                receipt_path=state.joinpath("profile-init.json")))
            if result.exit_code:
                raise _runtime_errors.RunnerError("docker_control_failed")
    except CleanupUnconfirmedError:
        raise _runtime_errors.RunnerError("container_termination_unverified") from None
    except (RuntimeError, DockerException):
        raise _runtime_errors.RunnerError("docker_control_failed") from None


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


