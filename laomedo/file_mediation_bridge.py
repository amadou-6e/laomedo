"""Network-free request transport for an independently hosted mediator.

The agent writes only to its disposable workspace. This host worker obtains
the grant from the accepted lease and keeps responses outside that workspace.
The mediator ledger remains authoritative for every effect and retry.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import threading
import time
from uuid import UUID, uuid4

from .github_mediation import MediationError, MediationStore, OPERATIONS, _request_hash


REQUEST_NAME = re.compile(r"^\.laomedo-req-([a-z0-9][a-z0-9._-]{0,63})\.json$")
MAX_REQUEST_BYTES = 1024 * 1024
REPARSE_POINT = 0x400


def _plain_file(path: Path) -> bool:
    try:
        entry = path.lstat()
    except OSError:
        return False
    return (stat.S_ISREG(entry.st_mode) and entry.st_nlink == 1 and
            not bool(getattr(entry, "st_file_attributes", 0) & REPARSE_POINT))


def _read_private_json(path: Path) -> dict | None:
    if not _plain_file(path) or path.stat().st_size > MAX_REQUEST_BYTES:
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


class FileMediationBridge:
    """Poll host-derived run paths and claim agent files into a private spool."""

    def __init__(self, runs_root: Path, lease_root: Path, store: MediationStore,
                 transport, journal: Path):
        self.runs_root = runs_root.resolve()
        self.lease_root = lease_root.resolve()
        self.store = store
        self.transport = transport
        self.journal = journal
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        self.failed_at = {}

    def serve(self, stop: threading.Event, status: Path) -> None:
        """Keep the independent service observable without dispatching runs."""
        status.parent.mkdir(parents=True, exist_ok=True)
        while not stop.is_set():
            try:
                pending = status.with_suffix(".pending")
                pending.write_text(json.dumps({"pid": os.getpid(),
                                               "at_monotonic": time.monotonic()}),
                                   encoding="utf-8")
                for attempt in range(5):
                    try:
                        os.replace(pending, status)
                        break
                    except PermissionError:
                        if attempt == 4:
                            raise
                        time.sleep(.01)
                self.poll_once()
            except Exception as error:
                # A bad run cannot permanently disable mediation for others.
                try:
                    self._record({"category": "bridge_poll_error",
                                  "exception_type": type(error).__name__,
                                  "at_monotonic": time.monotonic()})
                except OSError:
                    pass
            stop.wait(.1)

    def _record(self, value: dict) -> None:
        with self.journal.open("a", encoding="utf-8", newline="\n") as output:
            output.write(json.dumps(value, sort_keys=True) + "\n")

    def _item_failed(self, run_id: str, effect_id: str, error: Exception) -> None:
        key = (run_id, effect_id)
        now = time.monotonic()
        if now - self.failed_at.get(key, -100) < 5:
            return
        self.failed_at[key] = now
        try:
            self._record({"category": "bridge_item_error", "run_id": run_id,
                          "effect_id": effect_id,
                          "exception_type": type(error).__name__,
                          "at_monotonic": now})
        except OSError:
            pass

    def _run_paths(self, lease_dir: Path) -> tuple[str, Path, Path, Path, str] | None:
        lease = _read_private_json(lease_dir / "lease.json")
        accepted = _read_private_json(lease_dir / "accepted.json")
        if (lease is None or accepted is None or
                not isinstance(lease.get("token"), str) or
                lease["token"] != lease_dir.name or
                lease["token"] != accepted.get("token")):
            return None
        run_id = lease.get("run_id")
        try:
            run_id = str(UUID(run_id))
        except (ValueError, TypeError, AttributeError):
            return None
        if not isinstance(accepted.get("grant_id"), str):
            return None
        run_dir = self.runs_root / run_id
        if not run_dir.is_dir() or run_dir.is_symlink() or run_dir.resolve().parent != self.runs_root:
            return None
        record = _read_private_json(run_dir / "record.json")
        ownership = (record or {}).get("container_ownership") or {}
        if (record is None or record.get("run_id") != run_id or
                ownership.get("launch_token") != lease["token"] or
                ownership.get("grant_id") != accepted["grant_id"]):
            return None
        workspace = run_dir / "workspace"
        if not workspace.is_dir() or workspace.is_symlink() or workspace.resolve().parent != run_dir:
            return None
        secret = lease_dir / "grant.secret"
        if not _plain_file(secret) or secret.stat().st_size > 256:
            return None
        spool = run_dir / "bridge-spool"
        responses = run_dir / "bridge-responses"
        if not all(path.is_dir() and not path.is_symlink() and
                   path.resolve().parent == run_dir for path in (spool, responses)):
            return None
        try:
            token = secret.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return None
        if not token or any(char.isspace() for char in token):
            return None
        return run_id, workspace, spool, responses, token

    def _process(self, run_id: str, effect_id: str, claimed: Path,
                 responses: Path, token: str) -> None:
        response_path = responses / (effect_id + ".json")
        if response_path.exists():
            return
        claimed_at = time.monotonic()
        called = False
        replayed = False
        entered_store = False
        operation = None
        outcome = {"state": "rejected", "error": "request_invalid"}
        try:
            if not _plain_file(claimed) or claimed.stat().st_size > MAX_REQUEST_BYTES:
                raise ValueError("request_file_invalid")
            raw = claimed.read_bytes()
            if len(raw) > MAX_REQUEST_BYTES:
                raise ValueError("request_too_large")
            request = json.loads(raw)
            if not isinstance(request, dict) or request.get("effect_id") != effect_id:
                raise ValueError("request_invalid")
            operation = request.get("operation")

            def stored_outcome():
                stored = self.store.effect(run_id, effect_id)
                if stored is None:
                    return None
                digest = _request_hash(request.get("repository"), operation,
                                       request.get("payload"))
                if stored["request_hash"] != digest:
                    return {"state": "rejected", "error": "effect_conflict"}
                if stored["state"] == "confirmed":
                    return {"state": "confirmed",
                            "result": json.loads(stored["result_json"])}
                if stored["state"] == "rejected":
                    return {"state": "rejected", "error": stored["error_code"]}
                return {"state": "unknown"}

            entered_store = True
            outcome = stored_outcome()
            if outcome is not None:
                replayed = True
            else:
                def call_transport(repository, selected_operation, payload, **binding):
                    nonlocal called
                    called = True
                    return self.transport(repository, selected_operation, payload, **binding)

                try:
                    outcome = self.store.invoke(
                        token=token, repository=request.get("repository"),
                        operation=operation, payload=request.get("payload"),
                        effect_id=effect_id, transport=call_transport)
                except MediationError as error:
                    prior = stored_outcome()
                    outcome = prior or {"state": "rejected", "error": error.code}
                    replayed = prior is not None
                except Exception:
                    # The ledger may hold an unknown intent after a crash or
                    # database error. Never turn that into a denial.
                    prior = stored_outcome()
                    outcome = prior or {"state": "unknown"}
                    replayed = prior is not None
        except MediationError as error:
            outcome = ({"state": "unknown"} if entered_store else
                       {"state": "rejected", "error": error.code})
        except Exception:
            outcome = ({"state": "unknown"} if entered_store else
                       {"state": "rejected", "error": "request_invalid"})
        finished_at = time.monotonic()
        audit = {"run_id": run_id, "effect_id": effect_id,
                 "operation": (operation if isinstance(operation, str) and
                               operation in OPERATIONS else None),
                 "claimed_at_monotonic": claimed_at,
                 "finished_at_monotonic": finished_at,
                 "state": outcome.get("state"), "error": outcome.get("error"),
                 "provider_called": called, "replayed": replayed}
        self._record(audit)
        pending = responses / (effect_id + "." + uuid4().hex + ".pending")
        pending.write_text(json.dumps(outcome, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(pending, response_path)

    def poll_once(self) -> int:
        processed = 0
        leases = self.lease_root / "leases"
        if not leases.is_dir():
            return 0
        for lease_dir in leases.iterdir():
            if not lease_dir.is_dir() or lease_dir.is_symlink():
                continue
            try:
                paths = self._run_paths(lease_dir)
            except Exception as error:
                self._item_failed("unresolved", "lease-path", error)
                continue
            if paths is None:
                continue
            run_id, workspace, spool, responses, token = paths
            try:
                spool_items = list(spool.iterdir())
                workspace_items = list(workspace.iterdir())
            except OSError as error:
                self._item_failed(run_id, "directory-scan", error)
                continue
            # A crashed bridge may have claimed a request before receiving a
            # mediator answer. Replaying its *same* effect ID is safe only
            # because MediationStore resolves confirmed/unknown identities.
            for claimed in spool_items:
                match = REQUEST_NAME.fullmatch(claimed.name)
                if match and not (responses / (match.group(1) + ".json")).exists():
                    try:
                        self._process(run_id, match.group(1), claimed, responses, token)
                    except Exception as error:
                        self._item_failed(run_id, match.group(1), error)
                    else:
                        processed += 1
            for source in workspace_items:
                match = REQUEST_NAME.fullmatch(source.name)
                if match is None:
                    continue
                effect_id = match.group(1)
                claimed = spool / source.name
                if (claimed.exists() or claimed.is_symlink() or
                        (responses / (effect_id + ".json")).exists()):
                    continue
                for attempt in range(5):
                    try:
                        os.replace(source, claimed)
                        break
                    except PermissionError:
                        if attempt == 4:
                            break
                        time.sleep(.01)
                    except FileNotFoundError:
                        break
                    except OSError as error:
                        self._item_failed(run_id, effect_id, error)
                        break
                if not claimed.exists() and not claimed.is_symlink():
                    continue
                try:
                    self._process(run_id, effect_id, claimed, responses, token)
                except Exception as error:
                    self._item_failed(run_id, effect_id, error)
                else:
                    processed += 1
        return processed
