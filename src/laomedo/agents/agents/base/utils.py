"""Provider-neutral private state and workspace helpers."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID
from uuid import uuid4
import json
from laomedo.agents.errors import RunnerError
import os
import time


def failure_observation(error=None, *, stage="execution", code=None):
    """Observe only known exception types and fixed scalars; never inspect receipts.

    Unknown or dynamic metadata is omitted. Diagnostic failures return None and
    cannot replace the execution or cleanup error being observed.
    """
    try:
        from laomedo.agents.agents.base.models import FailureObservation
        from laomedo.agents.agents.base.settings import SDK_FAILURE_CODES

        if type(error) is RunnerError:
            if type(error.observation) is FailureObservation:
                return error.observation
            code = error.code if code is None else code
        try:
            from py_docker.errors import (
                DockerOperationError,
                ConnectionConfigurationError,
                OwnershipConflictError,
                ImageResolutionError,
                OutputLimitError,
                DeadlineError,
                JobCancelledError,
                CreationUnconfirmedError,
                CreationRejectedError,
                CleanupUnconfirmedError,
                PendingReceiptError,
                ReceiptInUseError,
            )

            trusted_types = (
                DockerOperationError,
                ConnectionConfigurationError,
                OwnershipConflictError,
                ImageResolutionError,
                OutputLimitError,
                DeadlineError,
                JobCancelledError,
                CreationUnconfirmedError,
                CreationRejectedError,
                CleanupUnconfirmedError,
                PendingReceiptError,
                ReceiptInUseError,
            )
        except ImportError:
            trusted_types = ()
        trusted = next((kind for kind in trusted_types if type(error) is kind), None)
        if trusted is None:
            return FailureObservation.from_values(stage=stage, code=code)
        name = trusted.__name__
        if trusted.code != SDK_FAILURE_CODES.get(name):
            return FailureObservation.from_values(stage=stage, code=code)
        primary = (
            error.primary
            if trusted in (CleanupUnconfirmedError, PendingReceiptError)
            else None
        )
        primary_type = next(
            (kind for kind in trusted_types if type(primary) is kind), None
        )
        if primary_type is not None and primary_type.code != SDK_FAILURE_CODES.get(
            primary_type.__name__
        ):
            primary_type = None
        return FailureObservation.from_values(
            stage=stage,
            code=code,
            sdk_class=name,
            sdk_code=trusted.code,
            operation=error.operation,
            primary_sdk_code=primary_type.code if primary_type is not None else None,
            primary_operation=primary.operation if primary_type is not None else None,
        )
    except Exception:
        return None


def _git_tree(path: Path) -> bool:
    return any((parent / ".git").exists() for parent in (path, *path.parents))


def _private(path: Path) -> Path:
    path = path.expanduser().resolve()
    if _git_tree(path) or path.is_symlink():
        raise RunnerError("private_state_must_be_outside_git")
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
        raise RunnerError("invalid_record")
    return value


def _id(value: str) -> str:
    if str(UUID(value)) != value:
        raise RunnerError("invalid_run_id")
    return value
