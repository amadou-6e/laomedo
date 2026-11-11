"""Internal retained-evidence normalization and stable, transactional cursor ownership."""

from contextlib import closing
from datetime import datetime, timezone
import json
import sqlite3

from laomedo.agents.activity.models import (
    ActivityPage,
    ActivityProjection,
    ActivityRecord,
    MessageActivity,
    ToolCallActivity,
    ToolResultActivity,
    UsageActivity,
)
from laomedo.agents.activity.runner.feed import read_feed
from laomedo.agents.agents.base.utils import _id, _read
from laomedo.agents.errors import RunnerError


class ActivityNormalizer:
    """Provider-internal normalization cache; never launches or controls native work."""

    MAX_RECEIPTS = 20000
    MAX_BYTES = 20 * 1024 * 1024

    def __init__(self, agent, projector, *, complete_from_snapshot=False):
        """Borrow the admitted Agent and its defining native projection function."""
        self.agent = agent
        self.projector = projector
        self.complete_from_snapshot = complete_from_snapshot

    def read(self, run_id, attempt_id, *, after=0, limit=100):
        """Publish immutable versions atomically and read a bounded normalized page."""
        if (
            type(after) is not int
            or after < 0
            or type(limit) is not int
            or not 1 <= limit <= 200
        ):
            raise RunnerError("invalid_activity_cursor")
        record = self.agent.status(run_id)
        root = self.agent._run_dir(run_id)
        _id(attempt_id)
        path = root / "activity-attempts" / (attempt_id + ".json")
        if not path.is_file():
            return ActivityPage(
                run_id=run_id,
                attempt_id=attempt_id,
                available=False,
                records=[],
                next_after=after,
                has_more=False,
                closed=False,
                complete=None,
                reason="activity_attempt_not_available",
            )
        try:
            with closing(
                sqlite3.connect(root / "activity-normalized.db", timeout=15)
            ) as db:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS records (attempt TEXT NOT NULL, sequence INTEGER NOT NULL, body TEXT NOT NULL, PRIMARY KEY(attempt,sequence))"
                )
                db.execute(
                    "CREATE TABLE IF NOT EXISTS snapshots (attempt TEXT PRIMARY KEY, state TEXT NOT NULL, projection TEXT NOT NULL, revision INTEGER NOT NULL)"
                )
                with db:
                    db.execute("BEGIN IMMEDIATE")
                    attempt = _read(path)
                    self._validate_attempt(attempt, attempt_id)
                    native = self._source(
                        root / "activity-events.jsonl",
                        attempt["native_start"],
                        attempt.get("native_end"),
                    )
                    telemetry = self._source(
                        root / "otel-events.jsonl",
                        attempt["otel_start"],
                        attempt.get("otel_end"),
                    )
                    # Native writers publish both ends together. A concurrent seal
                    # must constrain observations read while the initial record was open.
                    attempt = _read(path)
                    self._validate_attempt(attempt, attempt_id)
                    closed = attempt.get("native_end") is not None
                    if closed:
                        native = [
                            row
                            for row in native
                            if row["cursor"] <= attempt["native_end"]
                        ]
                        telemetry = [
                            row
                            for row in telemetry
                            if row["cursor"] <= attempt["otel_end"]
                        ]
                    rows = [
                        {
                            "raw": {
                                "method": "capture/usageBaseline",
                                "threads": attempt.get("usage_baseline", {}),
                                "fresh_thread": attempt.get("fresh_thread") is True,
                            },
                            "received_at": record.get("started_at")
                            or "1970-01-01T00:00:00+00:00",
                        }
                    ]
                    for source in (native, telemetry):
                        rows.extend(
                            {
                                "raw": {
                                    "event": row["event"],
                                    "received_at": row["received_at"],
                                },
                                "received_at": row["received_at"],
                            }
                            for row in source
                        )
                    projection = self.projector(
                        rows,
                        root_thread=record.get("thread_id"),
                        model=record.get("effective_model"),
                    )
                    if not isinstance(projection, ActivityProjection):
                        projection = ActivityProjection.model_validate(projection)
                    complete, reason = self._completion(attempt, native, closed)
                    total, revision = self._publish(db, attempt_id, projection)
                    if after > total:
                        raise RunnerError("invalid_activity_cursor")
                    values = db.execute(
                        "SELECT body FROM records WHERE attempt=? AND sequence>? ORDER BY sequence LIMIT ?",
                        (attempt_id, after, limit),
                    ).fetchall()
                    records = [
                        ActivityRecord.model_validate_json(value[0]) for value in values
                    ]
                    return ActivityPage(
                        run_id=run_id,
                        attempt_id=attempt_id,
                        available=True,
                        records=records,
                        next_after=records[-1].sequence if records else after,
                        has_more=(records[-1].sequence if records else after) < total,
                        closed=closed,
                        complete=complete,
                        reason=reason,
                        projection=projection,
                        projection_revision=revision,
                        status=attempt.get("status"),
                        thread_id=record.get("thread_id"),
                        model=record.get("effective_model"),
                        ended_at=attempt.get("ended_at"),
                    )
        except sqlite3.Error:
            raise RunnerError("activity_journal_unavailable") from None

    def _validate_attempt(self, attempt, identity):
        """Admit both source intervals without guessing closure from one source."""
        if attempt.get("id") != identity:
            raise RunnerError("activity_attempt_identity_mismatch")
        for source in ("native", "otel"):
            start, end = attempt.get(source + "_start"), attempt.get(source + "_end")
            if (
                type(start) is not int
                or start < 0
                or (end is not None and (type(end) is not int or end < start))
            ):
                raise RunnerError("activity_attempt_identity_mismatch")
        if (attempt.get("native_end") is None) != (attempt.get("otel_end") is None):
            raise RunnerError("activity_attempt_identity_mismatch")

    def _source(self, path, start, end):
        """Retain independent physical positions; never combine native/OTLP offsets."""
        rows, cursor, size = [], start, 0
        while True:
            page = read_feed(path, after=cursor, limit=200, before=end)
            rows.extend(page["events"])
            size += sum(
                len(json.dumps(row, ensure_ascii=False).encode("utf-8"))
                for row in page["events"]
            )
            if len(rows) > self.MAX_RECEIPTS or size > self.MAX_BYTES:
                raise RunnerError("activity_projection_limit")
            cursor = page["next_after"]
            if not page["has_more"]:
                return rows

    def _completion(self, attempt, native, closed):
        """Provider capture attestation is distinct from run success and resource cleanup."""
        if not closed:
            return None, None
        if self.complete_from_snapshot:
            terminal = (
                attempt.get("capture_complete", attempt.get("native_stream_complete"))
                is True
            )
        else:
            terminal = any(
                row["event"].get("method") == "turn/completed" for row in native
            )
        reason = attempt.get("capture_error")
        complete = terminal and not reason
        return bool(complete), (
            None
            if complete
            else reason
            or (
                "native_message_snapshot_only"
                if self.complete_from_snapshot
                else "native_terminal_event_not_observed"
            )
        )

    def _publish(self, db, attempt, projection):
        """Append changed snapshots without renumbering or rewriting earlier versions."""
        previous = db.execute(
            "SELECT state,projection,revision FROM snapshots WHERE attempt=?",
            (attempt,),
        ).fetchone()
        state = json.loads(previous[0]) if previous else {}
        payload = projection.to_payload()
        encoded = json.dumps(
            payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        revision = previous[2] if previous else 0
        total = db.execute(
            "SELECT COALESCE(MAX(sequence),0) FROM records WHERE attempt=?", (attempt,)
        ).fetchone()[0]
        if previous and previous[1] == encoded:
            return total, revision
        observed = datetime.now(timezone.utc)
        current = self._events(projection)
        # Late evidence can revoke an earlier known usage value. Publish unknown
        # instead of leaving the consumer's last known total looking authoritative.
        for key, value in state.items():
            if key not in current and value.get("kind") == "usage":
                current[key] = {
                    name: item if name in {"kind", "thread_id"} else None
                    for name, item in value.items()
                }
        for key, event in current.items():
            if state.get(key) != event:
                total += 1
                row = ActivityRecord(
                    sequence=total, occurred_at=None, observed_at=observed, event=event
                )
                db.execute(
                    "INSERT INTO records VALUES (?,?,?)",
                    (attempt, total, row.model_dump_json()),
                )
        revision += 1
        db.execute(
            "INSERT OR REPLACE INTO snapshots VALUES (?,?,?,?)",
            (attempt, json.dumps(current, sort_keys=True), encoded, revision),
        )
        return total, revision

    def _events(self, projection):
        """Translate already provider-interpreted items into common replacement records."""
        values = {}
        for entry in projection.items:
            item = entry.get("item", {})
            identity, thread = entry.get("id"), entry.get("thread")
            if (
                not isinstance(identity, str)
                or not identity
                or not isinstance(thread, str)
                or not thread
            ):
                continue
            key = json.dumps([thread, identity])
            kind = item.get("type")
            if kind in {"userMessage", "agentMessage", "reasoning"}:
                text = item.get("text")
                if isinstance(text, str):
                    event = MessageActivity(
                        message_id=identity,
                        thread_id=thread,
                        role="user" if kind == "userMessage" else "assistant",
                        text=text,
                    )
                    values["message:" + key] = event.model_dump(mode="json")
                continue
            arguments = item.get("arguments", item.get("input", {}))
            if not isinstance(arguments, dict):
                arguments = {"value": arguments}
            if kind == "commandExecution":
                arguments = {"command": item.get("command")}
            event = ToolCallActivity(
                tool_call_id=identity,
                thread_id=thread,
                name=str(item.get("tool") or kind or "unknown"),
                arguments=arguments,
            )
            values["call:" + key] = event.model_dump(mode="json")
            output = item.get("aggregatedOutput", item.get("output"))
            if output is not None and not isinstance(output, str):
                output = json.dumps(output, ensure_ascii=False)
            status = item.get("status")
            status = (
                "failed"
                if status in {"error", "failed"}
                else (
                    "cancelled"
                    if status in {"cancelled", "aborted"}
                    else "completed" if entry.get("ended") else "running"
                )
            )
            result = ToolResultActivity(
                tool_call_id=identity, thread_id=thread, status=status, output=output
            )
            values["result:" + key] = result.model_dump(mode="json")
        names = {
            "input_tokens": "inputTokens",
            "output_tokens": "outputTokens",
            "cached_input_tokens": "cachedInputTokens",
            "reasoning_output_tokens": "reasoningOutputTokens",
            "cache_write_input_tokens": "cacheWriteInputTokens",
            "total_tokens": "totalTokens",
        }
        for thread, counters in projection.usage_by_thread.items():
            if not isinstance(thread, str) or not thread:
                continue
            event = UsageActivity(
                thread_id=thread,
                **{
                    name: (counters or {}).get(native) for name, native in names.items()
                },
            )
            values["usage:" + thread] = event.model_dump(mode="json")
        return values
