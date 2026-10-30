"""Export bound native history offline without restoring a second execution wire."""

import hashlib
from contextlib import closing
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import time
from uuid import uuid4

from laomedo.agents.activity.redaction.utils import sanitized
from laomedo.agents.agents.opencode.history.settings import DATABASE_FILE
from laomedo.agents.agents.opencode.history.settings import EXPORT_SECONDS
from laomedo.agents.agents.opencode.history.settings import MAX_EXPORT_BYTES
from laomedo.agents.agents.opencode.history.settings import MAX_SESSIONS
from laomedo.agents.agents.opencode.history.settings import Settings
from laomedo.agents.agents.opencode.history.errors import HistoryError
from laomedo.agents.agents.opencode.history.models import (
    HistorySource,
    NativeExport,
    NativeHistory,
)
from laomedo.agents.errors import RunnerError


class HistoryReader:
    """Read only explicit session IDs; export jobs receive no live store or auth.

    Parameters
    ----------
    source : HistorySource
        Immutable provider bindings verified by the controller's launch owner.
    evidence : Path
        Private run evidence directory, outside the model's writable workspace.
    """

    def __init__(self, source: HistorySource, evidence: Path):
        """Retain the host-owned source; defer reads until the controller is closed."""
        self.source, self.evidence = source, Path(evidence)

    def read(self, session_id: str) -> NativeHistory:
        """Export one consistent native tree with no credentials, network or turns.

        A standard SQLite backup copies only the native database, not the profile.
        Native export then reads that private copy through the supported CLI.
        Every descendant must have an explicit task link and matching native parent.
        """
        from py_docker import Client
        from py_docker.errors import CleanupUnconfirmedError

        if not re.fullmatch(r"ses_[A-Za-z0-9]+", session_id):
            raise ValueError("Invalid native export identity")
        deadline = time.monotonic() + Settings().export_batch_seconds
        private = Path(tempfile.mkdtemp(prefix="history-", dir=self.evidence))
        unresolved = False
        try:
            self._copy_database(private / DATABASE_FILE)
            history = NativeHistory(root_id=session_id)
            pending = [(session_id, None)]
            total = 0
            with Client(environment={"DOCKER_HOST": self.source.endpoint}) as docker:
                while pending:
                    identity, parent = pending.pop()
                    if identity in history.sessions:
                        if history.sessions[identity].info.get("parentID") != parent:
                            raise ValueError(
                                "Native history tree is cyclic or has conflicting parents"
                            )
                        continue
                    if len(history.sessions) >= MAX_SESSIONS:
                        raise ValueError(
                            "Native history tree is cyclic or exceeds its bound"
                        )
                    # Reserve bounded process termination and receipt cleanup
                    # time inside the whole-tree budget, not once per child.
                    seconds = min(
                        EXPORT_SECONDS, int(deadline - time.monotonic()) - 15
                    )
                    if seconds < 1:
                        raise ValueError(
                            "Native history export batch exceeded its deadline"
                        )
                    payload = self._export(docker, private, identity, seconds)
                    total += len(payload)
                    if total > MAX_EXPORT_BYTES:
                        raise ValueError("Native history export exceeds its byte bound")
                    exported = NativeExport.model_validate_json(payload)
                    exported.bind(identity, parent)
                    history.sessions[identity] = exported
                    pending.extend((child, identity) for child in exported.child_ids())
            return history
        except CleanupUnconfirmedError:
            unresolved = True
            raise RunnerError("opencode_container_cleanup_unverified") from None
        finally:
            # An unresolved owned job may still reference its private copy.
            if not unresolved and private.resolve().parent == self.evidence.resolve():
                shutil.rmtree(private)

    def _copy_database(self, destination: Path) -> None:
        """Export a compact snapshot only after ruling out credential-store rows.

        Backup stays in host memory until its consistent schema/rows are checked.
        VACUUM INTO purges deleted-page contents before any copy reaches disk or
        a credential-free export job. No live profile is modified.
        """
        source = self.source.store / DATABASE_FILE
        limit = Settings().max_database_bytes
        if source.stat().st_size > limit:
            raise HistoryError("opencode_history_database_limit")
        deadline = time.monotonic() + 10

        page_size = 4096

        def progress(status, remaining, total):
            """Bound lock contention and database growth during the native backup."""
            if time.monotonic() > deadline or total * page_size > limit:
                raise ValueError("Native history backup exceeded its bound")

        with closing(
            sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
        ) as original:
            page_size = original.execute("PRAGMA page_size").fetchone()[0]
            with closing(sqlite3.connect(":memory:")) as snapshot:
                snapshot.execute("PRAGMA temp_store=MEMORY")
                original.backup(snapshot, pages=512, progress=progress, sleep=0.05)
                self._check_credentials(snapshot)
                snapshot.set_progress_handler(
                    lambda: int(time.monotonic() > deadline), 10000
                )
                snapshot.execute("VACUUM INTO ?", (str(destination),))

    def _check_credentials(self, database):
        """Require empty pinned account stores, including unexpected secret columns."""
        tables = {
            row[0]
            for row in database.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        required = {"account", "account_state", "control_account", "credential"}
        if not required <= tables:
            raise HistoryError("opencode_history_credentials_unverified")
        for table in tables:
            quoted = '"' + table.replace('"', '""') + '"'
            columns = [
                row[1] for row in database.execute("PRAGMA table_info(" + quoted + ")")
            ]
            if table == "session":
                columns = [
                    name
                    for name in columns
                    if name
                    not in {
                        "tokens_input",
                        "tokens_output",
                        "tokens_reasoning",
                        "tokens_cache_read",
                        "tokens_cache_write",
                    }
                ]
            sensitive = table in required or any(
                re.search(r"token|secret|password|credential|auth|(^|_)key($|_)|api.?key|bearer|cookie", name, re.I)
                for name in (table, *columns)
            )
            if (
                sensitive
                and database.execute("SELECT 1 FROM " + quoted + " LIMIT 1").fetchone()
                is not None
            ):
                raise HistoryError("opencode_history_credentials_present")

    def _export(self, docker, private: Path, session_id: str, seconds: int) -> bytes:
        """Run the pinned native export CLI for exactly one verified session ID."""
        from py_docker.containers.models import ContainerSpec, Mount
        from py_docker.jobs.models import ContainerJob
        from py_docker.streams.models import StreamLimits

        name = "laomedo-oc-history-" + uuid4().hex
        result = docker.jobs.run(
            ContainerJob(
                spec=ContainerSpec(
                    image=self.source.image_id,
                    name=name,
                    entrypoint=["timeout"],
                    command=[
                        "--signal=TERM",
                        "--kill-after=5s",
                        str(seconds),
                        "opencode",
                        "export",
                        session_id,
                    ],
                    user="10001:10001",
                    working_dir="/tmp",
                    network_mode="none",
                    read_only=False,
                    environment={
                        "HOME": "/home/runner",
                        "OPENCODE_DISABLE_PROJECT_CONFIG": "true",
                        "XDG_STATE_HOME": "/tmp/state",
                        "XDG_CONFIG_HOME": "/tmp/config",
                        "XDG_CACHE_HOME": "/tmp/cache",
                    },
                    mounts=[
                        Mount(
                            type="bind",
                            source=str(private),
                            target="/home/runner/.local/share/opencode",
                        )
                    ],
                ),
                limits=StreamLimits(
                    seconds=seconds + 10,
                    max_bytes=MAX_EXPORT_BYTES,
                ),
                wait_timeout_seconds=10.0,
                receipt_path=self.source.receipts / (name + ".json"),
            )
        )
        if result.exit_code:
            raise ValueError("Native history export did not complete")
        return result.stdout

    def retain(
        self, history: NativeHistory, baseline: NativeHistory | None, capture, catalogue
    ) -> None:
        """Retain source snapshots and project only new messages for this attempt.

        Once accepted, native snapshots are the sole usage/item source. The
        historical projection ignores ACP-derived items to avoid double counting.
        """
        if history.root_id != capture.session_id or (
            baseline and baseline.root_id != history.root_id
        ):
            raise ValueError("Native history attempt binding mismatch")
        raw = json.dumps(
            sanitized(
                {
                    "source": "native CLI export",
                    "before": baseline.model_dump(mode="json") if baseline else None,
                    "after": history.model_dump(mode="json"),
                }
            ),
            sort_keys=True,
        ).encode()
        digest = hashlib.sha256(raw).hexdigest()
        folder = self.evidence / "native-exports"
        folder.mkdir(exist_ok=True)
        folder.joinpath(digest + ".json").write_bytes(raw)
        events = [
            {
                "method": "opencode/modelCatalog",
                "params": {
                    "model": item["id"],
                    "rates": item.get("metadata", {}).get("cost"),
                    "source": "native CLI models --verbose",
                },
            }
            for item in catalogue
        ]
        events.insert(
            0,
            {
                "method": "opencode/exportStarted",
                "params": {
                    "source": "host capture boundary",
                    "snapshot_sha256": digest,
                },
            },
        )
        selected = history.attempt_sessions(baseline)
        for identity, exported in history.sessions.items():
            if identity not in selected:
                continue
            events.append(
                {
                    "method": "opencode/sessionSnapshot",
                    "params": {
                        "source": "native CLI export",
                        "snapshot_sha256": digest,
                        "source_received_at": history.captured_at.isoformat(),
                        "session": exported.info,
                    },
                }
            )
            events.append(
                {
                    "method": "opencode/messageSnapshot",
                    "params": {
                        "source": "native CLI export",
                        "snapshot_sha256": digest,
                        "source_received_at": history.captured_at.isoformat(),
                        "sessionID": identity,
                        "parentSessionID": exported.info.get("parentID"),
                        "messages": history.attempt_messages(identity, baseline),
                    },
                }
            )
        events.append(
            {
                "method": "opencode/exportCompleted",
                "params": {
                    "source": "host capture boundary",
                    "snapshot_sha256": digest,
                },
            }
        )
        capture.append_evidence_batch(events)
